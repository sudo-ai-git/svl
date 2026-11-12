"""Python benchmark: sieve of Eratosthenes, N = 100000 (pure Python)."""


def sieve(n=100_000):
    comp = [0] * (n + 1)
    i = 2
    while i * i <= n:
        if comp[i] == 0:
            for k in range(i * i, n + 1, i):
                comp[k] = 1
        i += 1
    return sum(1 for p in range(2, n + 1) if comp[p] == 0)


result = sieve()
print(result)
