
#ifndef EXP753_INFRA_INCLUDED
#define EXP753_INFRA_INCLUDED
// Required includes (already present in expert_dispatcher.cpp translation
// unit): <atomic> <chrono> <cstdint> <cstdio> <cstdlib> <functional> <thread>.
// This .inc is spliced into exactly ONE translation unit; the include guard and
// inline globals make it ODR-safe should that ever change.
// ---- exp753 execution-path timeline trace (measurement-only) ----------------
// Enabled by MOEI_EXP753_TRACE=1. Steady-state disabled cost is a single
// acquire load of the constant-initialized global flag g_exp753_enabled; the
// EXP753_REC* macros short-circuit on it, so when disabled NO hook argument is
// evaluated and no singleton, allocation, lock, I/O or CUDA call is touched.
// One-time lazy init (forced at library load) reads the env exactly once. When
// enabled, records append to a pre-allocated fixed ring (never grows, never
// blocks; on overflow it drops and counts). Each slot is published with a
// release store to a per-slot sequence flag; the flush reads slots with acquire
// loads and emits only committed slots, so concurrent recorders (route / exec /
// completion threads) can never produce torn reads. The ring is written to
// MOEI_EXP753_TRACE_FILE exactly once (global CAS guard) from an atexit handler;
// the singleton is heap-allocated and NEVER destroyed, so Get() can never
// dangle even if a worker thread records during exit. Flush does only CPU file
// I/O. This is pure observation: it changes no dispatch, routing, execution,
// retirement or completion decision.
enum Exp753Site : std::uint16_t {
  EXP753_SETINPUTS_ENTER = 1,      // SetInputs, new generation stored
  EXP753_SETINPUTS_EXIT = 2,       // SetInputs end; SetInputsWithInvocation
                                   // adds a second EXIT, expert=invocation_id
  EXP753_DISPATCH_ENTER = 3,       // DispatchExperts entry (caller thread)
  EXP753_DISPATCH_HF_LAUNCH = 4,   // cudaLaunchHostFunc(route) enqueued
  EXP753_ROUTE_CB_ENTER = 5,       // RouteReadyCallback on CUDA host thread
  EXP753_ROUTE_CB_PUSH = 6,        // route_queue_.Push done
  EXP753_ROUTE_FUNC_POP = 7,       // RouteFunc popped
  EXP753_ROUTE_FUNC_ENQUEUE = 8,   // EnqueueExpert issued for one expert
  EXP753_ROUTE_FUNC_DONE = 9,      // route handoff complete (pending set)
  EXP753_EXEC_PUSH = 10,           // exec_queue_.Push; payload 1=cache-hit,
                                   // 2=prefetch-wait, 3=fetch-transfer,
                                   // 4=grouped-prefill path
  EXP753_EXEC_POP = 11,            // GPUExecFunc popped ExecArgs (wakeup)
  EXP753_EXEC_FWD_ENTER = 12,      // before expert forward()
  EXP753_EXEC_FWD_RETURN = 13,     // forward() returned (host)
  EXP753_EXEC_OUTPUT_DONE = 14,    // OutputFunc returned
  EXP753_KERN_SAMPLE = 15,         // compute-timing pair retired;
                                   // payload = kernel_duration_ns (C arm only)
  EXP753_COMPLETE_ZERO = 16,       // CompleteOne dropped pending_ to 0
  EXP753_WAIT_ENTER = 17,          // WaitHiddenStates entered (caller)
  EXP753_WAIT_CV_WAKE = 18,        // caller cv predicate satisfied
  EXP753_WAIT_EXIT = 19,           // WaitHiddenStates normal return
  EXP753_COMPLETION_CB = 20,       // CompletionWaitsConsumedCallback entered
  EXP753_RETIRE_CB = 21,           // ExpertReadyToRetireCallback entered
};

struct Exp753Rec {
  std::uint16_t site;
  std::int32_t layer;
  std::int64_t expert;             // widened: SetInputsWithInvocation records
                                   // the uint64 invocation_id here without
                                   // truncation
  std::uint64_t generation;
  std::int64_t ns;
  std::int64_t payload;
  std::uint64_t tid;
};

// Constant-initialized globals: the disabled fast path is a single atomic load
// of g_exp753_enabled with NO function-local-static guard variable. inline
// (C++17) so the .inc stays ODR-safe if ever included in >1 translation unit.
inline std::atomic<bool> g_exp753_enabled{false};
inline std::atomic<bool> g_exp753_flushed{false};

inline bool Exp753Enabled() {
  return g_exp753_enabled.load(std::memory_order_acquire);
}

class Exp753Tracer {
 public:
  // Heap-allocated and NEVER destroyed: Get() can never return a dangling
  // reference, even if a worker thread records during static destruction.
  static Exp753Tracer& Get() {
    static Exp753Tracer* instance = new Exp753Tracer();
    return *instance;
  }
  inline void Record(std::uint16_t site, std::int32_t layer,
                     std::int64_t expert, std::uint64_t generation,
                     std::int64_t payload = 0) noexcept {
    std::uint64_t idx = write_.fetch_add(1, std::memory_order_relaxed);
    if (idx >= kCapacity) return;  // overflow: counted as claimed-capacity in Flush
    Exp753Rec& r = ring_[idx];
    r.site = site;
    r.layer = layer;
    r.expert = expert;
    r.generation = generation;
    r.ns = SteadyNowNs();
    r.payload = payload;
    r.tid = Tid();
    seq_[idx].store(1, std::memory_order_release);  // publish committed slot
  }
  void Flush() noexcept {
    // Single-flush CAS guard. The file is complete after fclose below; no other
    // thread gates on g_exp753_flushed for file readiness, so claiming the flag
    // at entry is correct and idempotent.
    bool expected = false;
    if (!g_exp753_flushed.compare_exchange_strong(
            expected, true, std::memory_order_acq_rel))
      return;
    if (!g_exp753_enabled.load(std::memory_order_relaxed)) return;
    std::uint64_t claimed = write_.load(std::memory_order_relaxed);
    std::uint64_t n = claimed < kCapacity ? claimed : kCapacity;
    FILE* f = std::fopen(path_.c_str(), "w");
    if (!f) return;
    std::uint64_t committed = 0;
    for (std::uint64_t i = 0; i < n; ++i)
      if (seq_[i].load(std::memory_order_acquire) == 1) ++committed;
    std::uint64_t dropped = claimed > kCapacity ? claimed - kCapacity : 0;
    std::uint64_t uncommitted = n - committed;
    std::fprintf(f,
                 "{\"meta\":1,\"records\":%llu,\"dropped\":%llu,"
                 "\"uncommitted\":%llu,\"claimed\":%llu,\"capacity\":%llu}\n",
                 (unsigned long long)committed, (unsigned long long)dropped,
                 (unsigned long long)uncommitted, (unsigned long long)claimed,
                 (unsigned long long)kCapacity);
    // Single consistent count: emit at most `committed` records so meta.records
    // equals the number of emitted lines even if a worker commits a slot
    // between the counting pass and this pass (slots are write-once, so the
    // committed set only grows; capping at `committed` keeps meta exact).
    std::uint64_t emitted = 0;
    for (std::uint64_t i = 0; i < n && emitted < committed; ++i) {
      if (seq_[i].load(std::memory_order_acquire) != 1) continue;  // skip torn
      const Exp753Rec& r = ring_[i];
      std::fprintf(f,
                   "{\"s\":%u,\"l\":%d,\"e\":%lld,\"g\":%llu,\"ns\":%lld,"
                   "\"p\":%lld,\"t\":%llu}\n",
                   (unsigned)r.site, r.layer, (long long)r.expert,
                   (unsigned long long)r.generation, (long long)r.ns,
                   (long long)r.payload, (unsigned long long)r.tid);
      ++emitted;
    }
    std::fclose(f);
  }

 private:
  static constexpr std::uint64_t kCapacity = 8ull * 1024ull * 1024ull;
  Exp753Tracer() {
    const char* e = std::getenv("MOEI_EXP753_TRACE");
    bool on = (e && e[0] == '1');
    if (on) {
      // Allocate ONLY when enabled: the disabled path never allocates path_,
      // ring_ or seq_, and never registers atexit.
      const char* p = std::getenv("MOEI_EXP753_TRACE_FILE");
      path_ = (p && p[0]) ? std::string(p)
                          : std::string("/tmp/exp753_trace.jsonl");
      ring_ = static_cast<Exp753Rec*>(
          std::malloc(sizeof(Exp753Rec) * kCapacity));  // 8M x 48B = 384 MiB
      std::atomic<std::uint8_t>* seq =
          new (std::nothrow) std::atomic<std::uint8_t>[kCapacity]();
      if (!ring_ || !seq) {
        on = false;
        std::free(ring_);
        delete[] seq;
        ring_ = nullptr;
        seq_ = nullptr;
      } else {
        seq_ = seq;
        std::atexit([] { Exp753Tracer::Get().Flush(); });
      }
    }
    // Publish enabled only AFTER ring_/seq_ are visible (release here pairs
    // with the acquire load in Exp753Enabled()).
    g_exp753_enabled.store(on, std::memory_order_release);
  }
  static std::uint64_t Tid() {
    thread_local std::uint64_t t = static_cast<std::uint64_t>(
        std::hash<std::thread::id>{}(std::this_thread::get_id()));
    return t;
  }
  std::atomic<std::uint64_t> write_{0};
  Exp753Rec* ring_ = nullptr;
  std::atomic<std::uint8_t>* seq_ = nullptr;
  std::string path_;
};

// Force one-time init at library load so g_exp753_enabled reflects the env
// before any dispatch thread runs (single-threaded during .so dynamic init).
namespace {
[[maybe_unused]] const bool g_exp753_force_init =
    (::Exp753Tracer::Get(), true);
}  // namespace

#define EXP753_REC(site, layer, expert, gen)                         \
  do {                                                               \
    if (::Exp753Enabled())                                           \
      ::Exp753Tracer::Get().Record((site), (layer), (expert), (gen)); \
  } while (0)
#define EXP753_RECP(site, layer, expert, gen, payload)               \
  do {                                                               \
    if (::Exp753Enabled())                                           \
      ::Exp753Tracer::Get().Record((site), (layer), (expert), (gen), \
                                   (payload));                       \
  } while (0)
// ---------------------------------------------------------------------------
#endif  // EXP753_INFRA_INCLUDED
