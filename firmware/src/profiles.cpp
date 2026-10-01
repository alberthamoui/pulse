#include "profiles.h"

#include <algorithm>

#include "config.h"

bool selectCandidates(std::vector<Candidate>& ranked) {
  std::vector<Candidate> matches;
  for (const Candidate& c : ranked) {
    if (c.weight > 0.0f) matches.push_back(c);
  }

  if (matches.empty()) {
    std::sort(ranked.begin(), ranked.end(), [](const Candidate& a, const Candidate& b) {
      return strcasecmp(a.name.c_str(), b.name.c_str()) < 0;
    });
    return false;
  }

  std::stable_sort(matches.begin(), matches.end(),
                   [](const Candidate& a, const Candidate& b) { return a.weight > b.weight; });
  if (matches.size() > cfg::MAX_SUGGESTIONS) matches.resize(cfg::MAX_SUGGESTIONS);
  ranked = std::move(matches);
  return true;
}
