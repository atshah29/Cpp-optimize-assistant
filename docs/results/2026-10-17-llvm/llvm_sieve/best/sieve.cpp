#include <iostream>
#include <vector>
#include <list>
#include <cstdlib>
#include <algorithm>

using namespace std;

void sieve(list<int>& unknown, vector<int>& primes)
{
  if (unknown.empty()) return;
  int max_val = *max_element(unknown.begin(), unknown.end());
  vector<char> is_prime(max_val + 1, true);
  if (max_val >= 0) is_prime[0] = false;
  if (max_val >= 1) is_prime[1] = false;
  for (int p = 2; p * p <= max_val; ++p) {
    if (is_prime[p]) {
      for (int mult = p * p; mult <= max_val; mult += p)
        is_prime[mult] = false;
    }
  }
  for (int v : unknown) {
    if (is_prime[v]) primes.push_back(v);
  }
  unknown.clear();
}

int main(int argc, char *argv[]) 
{
#ifdef SMALL_PROBLEM_SIZE
#define LENGTH 50
#else
#define LENGTH 500
#endif
  size_t NUM = (argc == 2 ? (atoi(argv[1]) < 1 ? 1 : atoi(argv[1])): LENGTH);

  vector<int> primes;

  // run the sieve repeatedly
  while (NUM--) {
    list<int> integers;
    for (int i = 2; i < 8192; ++i)
      integers.push_back(i);
    primes.clear();
    sieve(integers, primes);
  }

  cout << "Count: " << primes.size() << endl;
  return 0;
}
