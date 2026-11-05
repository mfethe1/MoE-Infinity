// exp715 timing driver (OURS, not upstream). Same stdin format as upstream
// tests/cpp/unit/prefetch/eviction_policy_driver.cpp; for each query prints
// "<hits> <ns_per_access>" timing SimulateEvictionPolicy with steady_clock
// (trace parsing excluded). Links the unmodified upstream eviction_policy.cpp.
#include <chrono>
#include <iostream>
#include <string>
#include <vector>

#include "prefetch/eviction_policy.h"

int main() {
  std::size_t n = 0;
  std::cin >> n;
  std::vector<ExpertCacheKey> accesses;
  accesses.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    int layer = 0, expert = 0;
    std::cin >> layer >> expert;
    accesses.push_back(MakeExpertCacheKey(layer, expert));
  }
  std::size_t queries = 0;
  std::cin >> queries;
  for (std::size_t q = 0; q < queries; ++q) {
    std::string name;
    std::size_t capacity = 0;
    EvictionPolicyOptions options;
    std::cin >> name >> capacity >> options.num_layers >> options.lcnu_alpha >>
        options.lcnu_beta >> options.lcnu_prior;
    auto t0 = std::chrono::steady_clock::now();
    std::size_t hits = SimulateEvictionPolicy(name, accesses, capacity, options);
    auto t1 = std::chrono::steady_clock::now();
    double ns = std::chrono::duration<double, std::nano>(t1 - t0).count();
    std::cout << hits << " " << (n ? ns / static_cast<double>(n) : 0.0) << "\n";
  }
  return 0;
}
