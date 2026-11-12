/* C benchmark: sieve of Eratosthenes, N = 100000 (gcc -O2, native) */
#include <stdio.h>

static int comp[100001];

int main(void) {
    const int N = 100000;
    int count = 0;
    for (int i = 2; (long)i * i <= N; i++) {
        if (comp[i] == 0) {
            for (int k = i * i; k <= N; k += i) comp[k] = 1;
        }
    }
    for (int p = 2; p <= N; p++) if (comp[p] == 0) count++;
    printf("%d\n", count);
    return 0;
}
