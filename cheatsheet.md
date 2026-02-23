# Exhaustive Data Science Cheatsheet — Open-Book Exam

---

# WEEK 1: Python Foundations

---

## 1.1 Variables & Data Types

Python is **dynamically typed** — the interpreter infers type at runtime; no explicit declaration needed.

| Type | Example | Mutable? | Notes |
|------|---------|----------|-------|
| `int` | `x = 5` | Immutable | Arbitrary precision in Python |
| `float` | `x = 3.14` | Immutable | 64-bit double precision (IEEE 754) |
| `str` | `x = "hello"` | Immutable | Sequence of Unicode characters |
| `bool` | `x = True` | Immutable | Subclass of `int` (`True == 1`, `False == 0`) |
| `NoneType` | `x = None` | Immutable | Represents absence of value |

```python
x = 10          # int
y = 3.14        # float
name = "Alice"  # str
flag = True     # bool
nothing = None  # NoneType

type(x)         # <class 'int'>
isinstance(x, int)  # True
```

### Type Conversion (Casting)

```python
int("42")       # 42   — string to int
float("3.14")   # 3.14 — string to float
str(100)        # "100" — int to string
int(3.9)        # 3    — truncates, does NOT round
bool(0)         # False — 0, 0.0, "", [], {}, None are falsy
bool(1)         # True  — any non-zero/non-empty is truthy
```

**Pitfall:** `int("3.5")` raises `ValueError`. Must do `int(float("3.5"))`.

### Arithmetic Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `+` | Addition | `5 + 3 → 8` |
| `-` | Subtraction | `5 - 3 → 2` |
| `*` | Multiplication | `5 * 3 → 15` |
| `/` | True division | `7 / 2 → 3.5` |
| `//` | Floor division | `7 // 2 → 3` |
| `%` | Modulo | `7 % 2 → 1` |
| `**` | Exponentiation | `2 ** 3 → 8` |

**Pitfall:** `/` always returns `float` in Python 3 (`4 / 2 → 2.0`). Use `//` for integer division.

**Pitfall:** Floor division with negatives rounds toward negative infinity: `-7 // 2 → -4` (not `-3`).

---

## 1.2 Strings

Strings are **immutable sequences** of characters.

### String Methods

```python
s = "Hello, World!"

s.upper()          # "HELLO, WORLD!"
s.lower()          # "hello, world!"
s.title()          # "Hello, World!"
s.strip()          # Removes leading/trailing whitespace
s.lstrip()         # Left strip
s.rstrip()         # Right strip
s.replace("Hello", "Hi")  # "Hi, World!"
s.split(", ")      # ["Hello", "World!"]
s.find("World")    # 7 (index of first occurrence, -1 if not found)
s.count("l")       # 3
s.startswith("He") # True
s.endswith("!")    # True
", ".join(["a", "b", "c"])  # "a, b, c"
```

### f-Strings (Formatted String Literals)

```python
name = "Alice"
age = 25
pi = 3.14159

f"Name: {name}, Age: {age}"         # "Name: Alice, Age: 25"
f"Pi to 2 decimals: {pi:.2f}"       # "Pi to 2 decimals: 3.14"
f"Result: {2 + 3}"                   # "Result: 5"
f"{'hello':>10}"                     # "     hello"  (right-align, width 10)
f"{'hello':<10}"                     # "hello     "  (left-align)
f"{'hello':^10}"                     # "  hello   "  (center)
```

### String Indexing & Slicing

```python
s = "Python"
s[0]      # 'P'       — first character
s[-1]     # 'n'       — last character
s[0:3]    # 'Pyt'     — indices 0, 1, 2
s[::2]    # 'Pto'     — every second character
s[::-1]   # 'nohtyP'  — reversed
```

**Pitfall:** Strings are immutable. `s[0] = "p"` raises `TypeError`.

---

## 1.3 Control Flow

### if / elif / else

```python
x = 10
if x > 0:
    print("Positive")
elif x == 0:
    print("Zero")
else:
    print("Negative")
```

### Comparison & Logical Operators

| Operator | Meaning |
|----------|---------|
| `==` | Equal to |
| `!=` | Not equal to |
| `<`, `>`, `<=`, `>=` | Ordering comparisons |
| `and` | Logical AND |
| `or` | Logical OR |
| `not` | Logical NOT |
| `is` | Identity (same object in memory) |
| `in` | Membership |

**Pitfall:** `==` checks value equality; `is` checks identity (same memory location). `a = [1,2]; b = [1,2]; a == b → True; a is b → False`.

### for Loops

```python
# Iterate over a list
for item in [1, 2, 3]:
    print(item)

# range(start, stop, step) — stop is EXCLUSIVE
for i in range(0, 10, 2):   # 0, 2, 4, 6, 8
    print(i)

# enumerate gives (index, value) pairs
for i, val in enumerate(["a", "b", "c"]):
    print(i, val)  # 0 a, 1 b, 2 c
```

### while Loops

```python
count = 0
while count < 5:
    print(count)
    count += 1   # Don't forget to update or infinite loop!
```

### break, continue, pass

```python
for i in range(10):
    if i == 3:
        continue   # Skip this iteration
    if i == 7:
        break      # Exit the loop entirely
    print(i)       # Prints 0, 1, 2, 4, 5, 6

# pass — placeholder, does nothing
def my_func():
    pass  # To be implemented later
```

---

## 1.4 Functions

### Defining Functions

```python
def greet(name, greeting="Hello"):
    """Docstring: describes what the function does."""
    return f"{greeting}, {name}!"

greet("Alice")              # "Hello, Alice!"
greet("Bob", "Hi")          # "Hi, Bob!"
greet(greeting="Hey", name="Eve")  # Keyword arguments
```

### *args and **kwargs

```python
def flexible(*args, **kwargs):
    print(args)    # Tuple of positional args
    print(kwargs)  # Dict of keyword args

flexible(1, 2, 3, name="Alice", age=25)
# args = (1, 2, 3)
# kwargs = {'name': 'Alice', 'age': 25}
```

### Scope: Local vs Global

```python
x = 10           # Global scope

def my_func():
    x = 5        # Local scope — does NOT modify global x
    return x

my_func()        # 5
print(x)         # 10 — unchanged
```

**Pitfall:** To modify a global variable inside a function, use `global x`. But this is generally discouraged.

### Return Values

```python
def divide(a, b):
    if b == 0:
        return None      # Early return
    return a / b

# Functions without return statement return None implicitly
def no_return():
    print("Hello")

result = no_return()  # result is None
```

---

## 1.5 Data Structures

### 1.5.1 Lists — Mutable, Ordered, Indexed

```python
# Creation
my_list = [1, 2, 3, "hello", True]
empty = []
from_range = list(range(5))  # [0, 1, 2, 3, 4]
```

#### List Methods

```python
lst = [3, 1, 4, 1, 5]

lst.append(9)         # [3, 1, 4, 1, 5, 9] — add to end
lst.insert(0, 99)     # [99, 3, 1, 4, 1, 5, 9] — insert at index
lst.extend([6, 7])    # Adds multiple items to end
lst.remove(1)         # Removes FIRST occurrence of 1
lst.pop()             # Removes & returns last item
lst.pop(0)            # Removes & returns item at index 0
lst.sort()            # Sorts in-place (returns None!)
lst.reverse()         # Reverses in-place
lst.index(4)          # Index of first occurrence of 4
lst.count(1)          # Number of occurrences of 1
len(lst)              # Length of list
```

#### Slicing

```python
lst = [0, 1, 2, 3, 4, 5]
lst[1:4]     # [1, 2, 3]
lst[:3]      # [0, 1, 2]
lst[3:]      # [3, 4, 5]
lst[::2]     # [0, 2, 4]
lst[::-1]    # [5, 4, 3, 2, 1, 0] — reversed copy
```

**Pitfall — Aliasing vs Copying:**

```python
a = [1, 2, 3]
b = a           # b is an ALIAS — same object in memory
b.append(4)     # a is ALSO [1, 2, 3, 4]!

# Shallow copy — creates new list, but nested objects still shared
c = a.copy()    # or a[:] or list(a)
c.append(5)     # a is unchanged

# Deep copy — fully independent
import copy
d = copy.deepcopy(a)
```

**Pitfall:** `sorted(lst)` returns a NEW sorted list; `lst.sort()` sorts IN-PLACE and returns `None`.

```python
lst = [3, 1, 2]
new_lst = sorted(lst)  # new_lst = [1, 2, 3], lst unchanged
result = lst.sort()    # result is None, lst is now [1, 2, 3]
```

---

### 1.5.2 Tuples — Immutable, Ordered, Indexed

**Why tuples?** They are faster than lists, can be used as dictionary keys (hashable), and signal "this data shouldn't change."

```python
# Creation
t = (1, 2, 3)
single = (42,)       # Comma required for single-element tuple!
empty = ()
from_list = tuple([1, 2, 3])

# Indexing & slicing — same as lists
t[0]      # 1
t[1:]     # (2, 3)

# Unpacking
a, b, c = (1, 2, 3)
first, *rest = (1, 2, 3, 4)  # first=1, rest=[2, 3, 4]

# Tuple methods (only two!)
t.count(1)   # 1
t.index(2)   # 1
```

**Pitfall:** `t = (42)` is just an int with parentheses. Need `t = (42,)` for a tuple.

**Pitfall:** Tuples are immutable: `t[0] = 99` raises `TypeError`. But a tuple containing a mutable object (e.g., a list) allows mutation of that inner object.

```python
t = ([1, 2], 3)
t[0].append(99)  # OK! t = ([1, 2, 99], 3)
t[0] = [4, 5]    # TypeError — can't reassign the element itself
```

---

### 1.5.3 Sets — Unordered, Unique Elements, Mutable

**Why sets?** O(1) average membership testing, automatic deduplication, mathematical set operations.

```python
# Creation
s = {1, 2, 3}
empty_set = set()      # NOT {} — that creates an empty dict!
from_list = set([1, 2, 2, 3])  # {1, 2, 3} — duplicates removed

# Methods
s.add(4)          # {1, 2, 3, 4}
s.remove(2)       # Removes 2, raises KeyError if not found
s.discard(99)     # Removes if present, NO error if not found
s.pop()           # Removes and returns arbitrary element
s.clear()         # Empties the set
```

#### Set Operations

```python
A = {1, 2, 3, 4}
B = {3, 4, 5, 6}

A | B          # Union:        {1, 2, 3, 4, 5, 6}
A & B          # Intersection:  {3, 4}
A - B          # Difference:    {1, 2}  (in A but not in B)
A ^ B          # Symmetric Diff: {1, 2, 5, 6}  (in one but not both)
A <= B         # Subset check:  False
A >= B         # Superset check: False
```

**Pitfall:** Sets are **unordered** — no indexing (`s[0]` → `TypeError`), no slicing. Iteration order is not guaranteed.

**Pitfall:** Set elements must be **hashable** (immutable): numbers, strings, tuples OK. Lists, dicts, sets → `TypeError`.

```python
{[1, 2]}       # TypeError — lists are unhashable
{(1, 2)}       # OK — tuples are hashable
```

---

### 1.5.4 Dictionaries — Key-Value Pairs, Mutable, Ordered (3.7+)

```python
# Creation
d = {"name": "Alice", "age": 25, "scores": [90, 85]}
empty = {}
from_pairs = dict([("a", 1), ("b", 2)])
```

#### Dictionary Methods

```python
d = {"name": "Alice", "age": 25}

d["name"]              # "Alice" — access by key (KeyError if missing)
d.get("name")          # "Alice" — returns None if missing
d.get("gpa", 0.0)     # 0.0 — default value if key missing

d["gpa"] = 3.8         # Add/update key-value pair
del d["age"]           # Delete key-value pair
d.pop("name")          # Remove and return value

d.keys()               # dict_keys(['gpa'])
d.values()             # dict_values([3.8])
d.items()              # dict_items([('gpa', 3.8)])

"gpa" in d             # True — checks keys, not values
d.update({"x": 1, "y": 2})  # Merge another dict

# Iterate
for key, value in d.items():
    print(key, value)
```

#### Nested Dictionaries

```python
students = {
    "Alice": {"age": 25, "grades": [90, 85, 92]},
    "Bob":   {"age": 22, "grades": [78, 88, 95]}
}

students["Alice"]["grades"][0]  # 90
```

**Pitfall:** Dict keys must be **hashable** (immutable). Lists can't be keys. Tuples can.

---

### 1.5.5 Data Structure Comparison Table

| Feature | List | Tuple | Set | Dict |
|---------|------|-------|-----|------|
| Syntax | `[1,2,3]` | `(1,2,3)` | `{1,2,3}` | `{"a":1}` |
| Mutable? | Yes | **No** | Yes | Yes |
| Ordered? | Yes | Yes | **No** | Yes (3.7+) |
| Indexed? | Yes | Yes | **No** | By key |
| Duplicates? | Yes | Yes | **No** | Keys: No |
| Use case | General collection | Fixed data, dict keys | Unique items, membership | Key-value mapping |

---

## 1.6 Git & Version Control

### Why Version Control?

Version control tracks changes to files over time, enabling collaboration, history tracking, and safe experimentation via branching.

### Key Concepts

| Concept | Definition |
|---------|-----------|
| **Repository (Repo)** | A project folder tracked by Git |
| **Commit** | A snapshot of changes with a message |
| **Branch** | An independent line of development |
| **Main/Master** | The default primary branch |
| **Merge** | Combining changes from one branch into another |
| **Pull Request (PR)** | A request to merge changes, enabling code review |
| **Clone** | Copy a remote repository to local machine |
| **Fork** | Personal copy of someone else's repository |

### Basic Git Workflow

```bash
git init                    # Initialize a new repo
git clone <url>             # Clone existing repo

git status                  # Check status of working directory
git add <file>              # Stage file for commit
git add .                   # Stage all changes
git commit -m "message"     # Commit staged changes

git branch <name>           # Create new branch
git checkout <name>         # Switch to branch
git checkout -b <name>      # Create and switch in one step

git merge <branch>          # Merge branch into current branch
git pull                    # Fetch + merge from remote
git push                    # Push commits to remote
```

### Branching Strategy

1. Create a feature branch from `main`
2. Make changes and commit
3. Open a Pull Request for review
4. After approval, merge into `main`
5. Delete the feature branch

**Pitfall:** Always pull before pushing to avoid merge conflicts. Commit often with descriptive messages.

---
---

# WEEK 2: Probability & Distributions

---

## 2.1 Probability Fundamentals

### Key Definitions

- **Experiment:** A procedure that produces an outcome (e.g., rolling a die)
- **Sample Space (S):** The set of ALL possible outcomes (e.g., S = {1, 2, 3, 4, 5, 6})
- **Event:** A subset of the sample space (e.g., "rolling an even number" = {2, 4, 6})
- **Probability of an event A:**

$$P(A) = \frac{\text{Number of favorable outcomes}}{|\text{Sample Space}|}$$

Properties:
- $0 \leq P(A) \leq 1$
- $P(S) = 1$ (certain event)
- $P(\emptyset) = 0$ (impossible event)
- $P(A^c) = 1 - P(A)$ (complement)

### Counting Principles

**Multiplication Rule:** If task A can be done in $m$ ways and task B in $n$ ways, then A and B together can be done in $m \times n$ ways.

**Permutations** (order matters):
$$P(n, k) = \frac{n!}{(n-k)!}$$

**Combinations** (order doesn't matter):
$$C(n, k) = \binom{n}{k} = \frac{n!}{k!(n-k)!}$$

```python
from math import factorial, comb, perm

factorial(5)     # 120
comb(10, 3)      # 120  — "10 choose 3"
perm(10, 3)      # 720  — permutations
```

---

## 2.2 PMF, PDF, and CDF

### Discrete Random Variables → PMF

The **Probability Mass Function (PMF)** gives the probability that a discrete random variable equals a specific value.

$$P(X = x) = p(x), \quad \sum_{\text{all } x} p(x) = 1$$

**Example:** Fair die → $P(X = k) = \frac{1}{6}$ for $k \in \{1, 2, 3, 4, 5, 6\}$.

### Continuous Random Variables → PDF

The **Probability Density Function (PDF)** gives the density of probability at each point. For continuous variables, the probability at any **single** point is zero.

$$P(a \leq X \leq b) = \int_a^b f(x)\,dx$$

Properties:
- $f(x) \geq 0$ for all $x$
- $\int_{-\infty}^{\infty} f(x)\,dx = 1$

**Pitfall:** For continuous distributions, $P(X = x) = 0$. Only intervals have non-zero probability. The PDF value $f(x)$ is a **density**, not a probability — it can exceed 1.

### CDF (Cumulative Distribution Function)

The **CDF** gives the probability that $X$ is less than or equal to $x$:

$$F(x) = P(X \leq x)$$

- For discrete: $F(x) = \sum_{k \leq x} p(k)$
- For continuous: $F(x) = \int_{-\infty}^{x} f(t)\,dt$

Properties:
- $F(-\infty) = 0$, $F(\infty) = 1$
- $F$ is non-decreasing
- $P(a < X \leq b) = F(b) - F(a)$

**Relationship:** $f(x) = \frac{d}{dx} F(x)$ — the PDF is the derivative of the CDF.

---

## 2.3 Expected Value & Variance

### Expected Value (Mean)

$$E[X] = \mu = \begin{cases} \sum_x x \cdot p(x) & \text{(discrete)} \\ \int_{-\infty}^{\infty} x \cdot f(x)\,dx & \text{(continuous)} \end{cases}$$

**Interpretation:** The long-run average of the random variable over many trials.

### Variance & Standard Deviation

$$\text{Var}(X) = \sigma^2 = E[(X - \mu)^2] = E[X^2] - (E[X])^2$$

$$\text{SD}(X) = \sigma = \sqrt{\text{Var}(X)}$$

**Interpretation:** Variance measures the average squared deviation from the mean. Standard deviation is in the same units as $X$.

### Properties

$$E[aX + b] = aE[X] + b$$
$$\text{Var}(aX + b) = a^2 \text{Var}(X)$$

---

## 2.4 Histograms

### What is a Histogram?

A histogram divides data into **bins** (intervals) and shows the frequency (count) or density of observations in each bin.

```python
import matplotlib.pyplot as plt
import numpy as np

data = np.random.normal(0, 1, 1000)

# Basic frequency histogram
plt.hist(data, bins=30, edgecolor='black')
plt.xlabel("Value")
plt.ylabel("Frequency")
plt.title("Frequency Histogram")
plt.show()
```

### Normalized / Density Histogram

When `density=True`, the y-axis shows **probability density** so that the total **area** of all bars sums to 1 (not the heights!).

$$\text{Bar height} = \frac{\text{Relative frequency}}{\text{Bin width}}$$

```python
plt.hist(data, bins=30, density=True, edgecolor='black', alpha=0.7)

# Overlay the theoretical PDF
x = np.linspace(-4, 4, 100)
from scipy import stats
plt.plot(x, stats.norm.pdf(x, 0, 1), 'r-', linewidth=2)
plt.ylabel("Density")
plt.show()
```

**Pitfall:** With `density=True`, bar heights are NOT probabilities. The **area** of each bar (height × width) is the probability. Heights can exceed 1 for narrow bins.

### Bin Selection

- **Too few bins:** Over-smooths, hides structure
- **Too many bins:** Noisy, overfits to random variation
- Common rules: Sturges' rule (`bins = 1 + log2(n)`), Square root rule (`bins = √n`)
- `bins='auto'` in matplotlib uses a data-driven heuristic

---

## 2.5 Key Distributions

### 2.5.1 Bernoulli Distribution

A single trial with two outcomes: success ($X = 1$) with probability $p$, failure ($X = 0$) with probability $1 - p$.

$$P(X = k) = p^k (1-p)^{1-k}, \quad k \in \{0, 1\}$$

$$E[X] = p, \quad \text{Var}(X) = p(1-p)$$

```python
from scipy import stats

rv = stats.bernoulli(p=0.3)
rv.pmf(1)       # P(X=1) = 0.3
rv.pmf(0)       # P(X=0) = 0.7
rv.mean()       # 0.3
rv.var()        # 0.21
rv.rvs(size=10) # Generate 10 random samples
```

### 2.5.2 Binomial Distribution

Number of successes in $n$ **independent** Bernoulli trials, each with success probability $p$.

$$P(X = k) = \binom{n}{k} p^k (1-p)^{n-k}, \quad k = 0, 1, \ldots, n$$

$$E[X] = np, \quad \text{Var}(X) = np(1-p)$$

```python
rv = stats.binom(n=10, p=0.5)
rv.pmf(5)        # P(X=5) — exactly 5 successes
rv.cdf(5)        # P(X≤5)
rv.sf(5)         # P(X>5) = 1 - cdf(5) — survival function
rv.mean()        # 5.0
rv.var()         # 2.5
rv.rvs(size=100) # 100 random samples

# Plot PMF
k = np.arange(0, 11)
plt.bar(k, rv.pmf(k))
plt.xlabel("k (successes)")
plt.ylabel("P(X=k)")
plt.title("Binomial(n=10, p=0.5)")
plt.show()
```

**Pitfall:** Binomial assumes **independent, identical** trials. If trials are dependent or probabilities change, Binomial doesn't apply.

### 2.5.3 Gaussian (Normal) Distribution

The most fundamental continuous distribution — arises from CLT.

$$f(x) = \frac{1}{\sigma\sqrt{2\pi}} \exp\left(-\frac{(x - \mu)^2}{2\sigma^2}\right)$$

Parameters: $\mu$ (mean, center), $\sigma$ (standard deviation, spread).

**Standard Normal:** $Z \sim N(0, 1)$ — mean 0, standard deviation 1.

$$Z = \frac{X - \mu}{\sigma} \quad \text{(standardization / z-score)}$$

**Empirical Rule (68-95-99.7):**
- 68% of data within $\mu \pm 1\sigma$
- 95% within $\mu \pm 2\sigma$
- 99.7% within $\mu \pm 3\sigma$

```python
rv = stats.norm(loc=0, scale=1)   # loc=μ, scale=σ

rv.pdf(0)        # Density at x=0
rv.cdf(1.96)     # P(Z ≤ 1.96) ≈ 0.975
rv.ppf(0.975)    # Inverse CDF: z such that P(Z ≤ z) = 0.975 → ≈ 1.96
rv.sf(1.96)      # P(Z > 1.96) ≈ 0.025

# Generate samples
samples = rv.rvs(size=1000)

# Any normal: X ~ N(μ=100, σ=15)
rv2 = stats.norm(loc=100, scale=15)
rv2.cdf(115)     # P(X ≤ 115)
```

### 2.5.4 Exponential Distribution

Models time between events in a Poisson process (e.g., time between arrivals).

$$f(x) = \lambda e^{-\lambda x}, \quad x \geq 0$$

$$E[X] = \frac{1}{\lambda}, \quad \text{Var}(X) = \frac{1}{\lambda^2}$$

**Memoryless property:** $P(X > s + t \mid X > s) = P(X > t)$ — the distribution "forgets" the past.

```python
# scipy parameterizes as scale = 1/λ
lam = 2.0
rv = stats.expon(scale=1/lam)

rv.pdf(0.5)      # Density at x=0.5
rv.cdf(1.0)      # P(X ≤ 1)
rv.mean()        # 0.5 = 1/λ
rv.rvs(size=100) # Random samples
```

**Pitfall — scipy parameterization:** `scipy.stats.expon` uses `scale = 1/λ`, NOT `λ` directly. If $\lambda = 2$, use `scale=0.5`.

---

### 2.5.5 `scipy.stats` Unified Interface

| Method | Meaning |
|--------|---------|
| `.pmf(k)` | Probability mass at k (discrete) |
| `.pdf(x)` | Probability density at x (continuous) |
| `.cdf(x)` | $P(X \leq x)$ |
| `.sf(x)` | $P(X > x) = 1 - \text{cdf}(x)$ — survival function |
| `.ppf(q)` | Inverse CDF: value $x$ such that $P(X \leq x) = q$ (quantile function) |
| `.isf(q)` | Inverse survival: $x$ such that $P(X > x) = q$ |
| `.rvs(size=n)` | Generate $n$ random samples |
| `.mean()` | Expected value |
| `.var()` | Variance |
| `.std()` | Standard deviation |
| `.interval(alpha)` | Central interval containing fraction alpha |

---

## 2.6 Poisson Distribution

Models the number of events occurring in a fixed interval when events happen at a constant average rate $\lambda$.

$$P(X = k) = \frac{\lambda^k e^{-\lambda}}{k!}, \quad k = 0, 1, 2, \ldots$$

$$E[X] = \lambda, \quad \text{Var}(X) = \lambda$$

```python
rv = stats.poisson(mu=5)   # λ = 5
rv.pmf(3)                   # P(X=3)
rv.cdf(5)                   # P(X ≤ 5)
```

**Key property:** Mean equals variance ($E[X] = \text{Var}(X) = \lambda$).

---
---

# WEEK 4: Sampling, Estimation & Functional Python

---

## 4.1 Population vs. Sample

| Concept | Population | Sample |
|---------|-----------|--------|
| Definition | The **entire** group of interest | A **subset** selected from the population |
| Size notation | $N$ | $n$ |
| Goal | Describe the whole group | Make **inferences** about the population |

**Why sample?** It's often impractical or impossible to measure every member of a population. Sampling lets us draw conclusions about the population using manageable amounts of data.

### Parameters vs. Statistics

| | Parameter (Population) | Statistic (Sample) |
|--|----------------------|-------------------|
| Mean | $\mu = \frac{1}{N}\sum_{i=1}^N x_i$ | $\bar{x} = \frac{1}{n}\sum_{i=1}^n x_i$ |
| Variance | $\sigma^2 = \frac{1}{N}\sum(x_i - \mu)^2$ | $s^2 = \frac{1}{n-1}\sum(x_i - \bar{x})^2$ |
| Std Dev | $\sigma$ | $s$ |
| Proportion | $p$ | $\hat{p}$ |

**Key insight:** Parameters are fixed but usually unknown. Statistics are calculated from data and vary from sample to sample.

### Bessel's Correction (n − 1)

Sample variance divides by $n-1$ instead of $n$:

$$s^2 = \frac{1}{n-1}\sum_{i=1}^n (x_i - \bar{x})^2$$

**Why?** Dividing by $n$ systematically **underestimates** the true population variance because the sample mean $\bar{x}$ is closer to the sample data points than the true population mean $\mu$. Dividing by $n-1$ corrects this bias, making $s^2$ an **unbiased estimator** of $\sigma^2$.

```python
import numpy as np

data = [4, 7, 13, 2, 1]
np.var(data)          # Population variance (divides by N)
np.var(data, ddof=1)  # Sample variance (divides by N-1) ← USE THIS
np.std(data, ddof=1)  # Sample standard deviation
```

**Pitfall:** `np.var()` defaults to population variance (ddof=0). For sample variance, always use `ddof=1`.

---

## 4.2 Sampling Distributions

### What is a Sampling Distribution?

If you repeatedly draw samples of size $n$ from a population, compute a statistic (e.g., $\bar{x}$) for each sample, the distribution of those statistics is the **sampling distribution**.

**Key properties of the sampling distribution of $\bar{X}$:**

$$E[\bar{X}] = \mu \quad \text{(unbiased)}$$

$$\text{Var}(\bar{X}) = \frac{\sigma^2}{n}$$

$$\text{SE}(\bar{X}) = \frac{\sigma}{\sqrt{n}} \quad \text{(Standard Error)}$$

**Interpretation:** The standard error measures how much $\bar{x}$ varies from sample to sample. Larger $n$ → smaller SE → more precise estimates.

```python
# Simulating a sampling distribution
population = np.random.exponential(scale=2, size=100000)
sample_means = []

for _ in range(10000):
    sample = np.random.choice(population, size=30, replace=False)
    sample_means.append(np.mean(sample))

print(f"Mean of sample means: {np.mean(sample_means):.4f}")
print(f"Std of sample means (SE): {np.std(sample_means):.4f}")
print(f"Theoretical SE: {np.std(population)/np.sqrt(30):.4f}")
```

---

## 4.3 Law of Large Numbers (LLN)

**Statement:** As sample size $n \to \infty$, the sample mean $\bar{X}_n$ converges to the population mean $\mu$.

$$\bar{X}_n = \frac{1}{n}\sum_{i=1}^n X_i \xrightarrow{n \to \infty} \mu$$

**Interpretation:** With enough data, the sample average is a good approximation of the true mean. This justifies using sample statistics to estimate population parameters.

```python
# Demonstration: rolling a fair die
np.random.seed(42)
rolls = np.random.randint(1, 7, size=10000)

# Running average converges to 3.5
running_avg = np.cumsum(rolls) / np.arange(1, 10001)

plt.plot(running_avg)
plt.axhline(y=3.5, color='r', linestyle='--', label='True mean = 3.5')
plt.xlabel("Number of rolls")
plt.ylabel("Running average")
plt.title("Law of Large Numbers")
plt.legend()
plt.show()
```

**Pitfall — Gambler's Fallacy:** LLN does NOT mean short-run outcomes "balance out." Each trial is independent. After 10 heads in a row, the next flip is still 50/50.

---

## 4.4 Central Limit Theorem (CLT)

**Statement:** For **any** population with mean $\mu$ and finite variance $\sigma^2$, the distribution of the sample mean $\bar{X}_n$ approaches a normal distribution as $n$ increases:

$$\bar{X}_n \xrightarrow{d} N\left(\mu, \frac{\sigma^2}{n}\right) \quad \text{as } n \to \infty$$

Or equivalently, the standardized version:

$$Z = \frac{\bar{X}_n - \mu}{\sigma / \sqrt{n}} \xrightarrow{d} N(0, 1)$$

### Why CLT Matters

- **Universality:** Works regardless of the population's shape (uniform, skewed, bimodal, etc.)
- **Foundation for inference:** Enables confidence intervals and hypothesis tests even when the population isn't normal
- **Rule of thumb:** $n \geq 30$ is usually sufficient for a good normal approximation

```python
# CLT demonstration: sample means from a UNIFORM distribution
from scipy import stats

population = stats.uniform(0, 1)  # Uniform[0,1], NOT normal!
sample_sizes = [5, 15, 30, 100]

fig, axes = plt.subplots(1, 4, figsize=(16, 4))
for ax, n in zip(axes, sample_sizes):
    means = [population.rvs(size=n).mean() for _ in range(5000)]
    ax.hist(means, bins=40, density=True, alpha=0.7)
    ax.set_title(f"n = {n}")
    ax.set_xlabel("Sample Mean")

plt.suptitle("CLT: Sample Means from Uniform Distribution")
plt.tight_layout()
plt.show()
```

**Key takeaway:** Even though the original distribution is uniform (flat), the distribution of sample means becomes bell-shaped as $n$ increases.

---

## 4.5 Functional Python

### 4.5.1 Lambda Functions

Anonymous (unnamed) functions for short, single-expression operations.

```python
# Syntax: lambda arguments: expression
square = lambda x: x ** 2
square(5)   # 25

add = lambda x, y: x + y
add(3, 4)   # 7

# Useful for sorting
students = [("Alice", 90), ("Bob", 85), ("Eve", 95)]
sorted(students, key=lambda s: s[1])               # Sort by grade
sorted(students, key=lambda s: s[1], reverse=True)  # Descending
```

**Pitfall:** Lambdas are limited to a single expression. For multi-line logic, use `def`.

### 4.5.2 List Comprehensions

Concise way to create lists (and other collections) by transforming and/or filtering iterables.

```python
# Basic: [expression for item in iterable]
squares = [x**2 for x in range(10)]           # [0, 1, 4, 9, ..., 81]

# With condition: [expression for item in iterable if condition]
evens = [x for x in range(20) if x % 2 == 0]  # [0, 2, 4, ..., 18]

# Nested loops
pairs = [(x, y) for x in range(3) for y in range(3)]
# [(0,0), (0,1), (0,2), (1,0), (1,1), (1,2), (2,0), (2,1), (2,2)]

# Dict comprehension
word_lengths = {w: len(w) for w in ["hello", "world", "python"]}
# {'hello': 5, 'world': 5, 'python': 6}

# Set comprehension
unique_lengths = {len(w) for w in ["hello", "world", "python"]}
# {5, 6}
```

### 4.5.3 Higher-Order Functions: map, filter, reduce

**Higher-order functions** take other functions as arguments.

#### `map(function, iterable)` — Apply function to every element

```python
numbers = [1, 2, 3, 4, 5]
squared = list(map(lambda x: x**2, numbers))   # [1, 4, 9, 16, 25]

# Equivalent list comprehension:
squared = [x**2 for x in numbers]
```

#### `filter(function, iterable)` — Keep elements where function returns True

```python
numbers = [1, 2, 3, 4, 5, 6]
evens = list(filter(lambda x: x % 2 == 0, numbers))  # [2, 4, 6]

# Equivalent list comprehension:
evens = [x for x in numbers if x % 2 == 0]
```

#### `reduce(function, iterable)` — Accumulate a single result

```python
from functools import reduce

numbers = [1, 2, 3, 4, 5]
total = reduce(lambda acc, x: acc + x, numbers)  # 15
# Step by step: ((((1+2)+3)+4)+5)

product = reduce(lambda acc, x: acc * x, numbers)  # 120
```

### Comparison: Loop vs Comprehension vs map/filter

```python
# Task: get squares of even numbers from 0-9
# Loop approach
result = []
for x in range(10):
    if x % 2 == 0:
        result.append(x**2)

# List comprehension (most Pythonic)
result = [x**2 for x in range(10) if x % 2 == 0]

# map + filter approach
result = list(map(lambda x: x**2, filter(lambda x: x % 2 == 0, range(10))))
```

**Best practice:** Prefer list comprehensions for readability. Use `map`/`filter` when passing an existing named function.

---
---

# WEEK 5: Statistical Inference

---

## 5.1 Hypothesis Testing Framework

### The Logic of Hypothesis Testing

Hypothesis testing asks: "Is the observed effect real, or could it be due to chance?"

1. **Assume** the null hypothesis $H_0$ is true
2. **Calculate** how likely the observed data (or more extreme) would be under $H_0$
3. If very unlikely → **reject** $H_0$ in favor of $H_1$

### Null vs. Alternative Hypotheses

| | Symbol | Meaning |
|---|--------|---------|
| **Null Hypothesis** | $H_0$ | Default assumption, "no effect" / "no difference" |
| **Alternative Hypothesis** | $H_1$ (or $H_a$) | What we're trying to find evidence for |

**Examples:**
- Testing a coin: $H_0: p = 0.5$ vs. $H_1: p \neq 0.5$ (two-tailed)
- Testing a drug: $H_0: \mu_{\text{drug}} = \mu_{\text{placebo}}$ vs. $H_1: \mu_{\text{drug}} > \mu_{\text{placebo}}$ (one-tailed)

### One-Tailed vs. Two-Tailed Tests

| | One-Tailed | Two-Tailed |
|---|-----------|-----------|
| $H_1$ | $\mu > \mu_0$ or $\mu < \mu_0$ | $\mu \neq \mu_0$ |
| Rejection region | One tail | Both tails |
| Use when | Direction of effect is predicted | Only testing for any difference |
| Critical value (α=0.05) | $z = 1.645$ (one side) | $z = \pm 1.96$ (both sides) |

---

## 5.2 Significance Level, P-value, and Decision Rules

### Significance Level ($\alpha$)

The **significance level** $\alpha$ is the probability of rejecting $H_0$ when it is actually true (Type I error rate). Common choices: $\alpha = 0.05$ (5%) or $\alpha = 0.01$ (1%).

### P-value

The **p-value** is the probability of observing data **as extreme or more extreme** than what was observed, assuming $H_0$ is true.

**Decision rule:**
- If $p\text{-value} \leq \alpha$ → **Reject** $H_0$ (result is "statistically significant")
- If $p\text{-value} > \alpha$ → **Fail to reject** $H_0$ (not enough evidence)

**Pitfall:** "Fail to reject $H_0$" ≠ "Accept $H_0$." Absence of evidence is not evidence of absence. The test may lack statistical power.

**Pitfall:** A small p-value does NOT mean the effect is large or practically important. It only means the result is unlikely under $H_0$. Statistical significance ≠ practical significance.

---

## 5.3 Type I and Type II Errors

| | $H_0$ is True | $H_0$ is False |
|---|--------------|----------------|
| **Reject $H_0$** | **Type I Error** (False Positive), prob = $\alpha$ | Correct! (True Positive), prob = $1 - \beta$ = **Power** |
| **Fail to Reject $H_0$** | Correct! (True Negative) | **Type II Error** (False Negative), prob = $\beta$ |

- **Type I Error ($\alpha$):** Concluding there's an effect when there isn't one
- **Type II Error ($\beta$):** Failing to detect a real effect
- **Power ($1 - \beta$):** Probability of correctly rejecting a false $H_0$

**Trade-off:** Decreasing $\alpha$ (more conservative) increases $\beta$ (harder to detect real effects). Increasing sample size $n$ reduces both.

---

## 5.4 Z-Test

### When to Use

- Population standard deviation $\sigma$ is **known**
- Sample size is large ($n \geq 30$) — by CLT, sampling distribution is approximately normal
- OR population is normally distributed

### Test Statistic

$$z = \frac{\bar{x} - \mu_0}{\sigma / \sqrt{n}}$$

where $\mu_0$ is the hypothesized population mean.

### Z-Test in Python

```python
from scipy import stats
import numpy as np

# Example: Testing if mean differs from 100
sample = np.array([102, 98, 105, 99, 101, 103, 97, 104, 100, 106])
mu_0 = 100           # Hypothesized mean
sigma = 3            # Known population std dev
n = len(sample)
x_bar = np.mean(sample)

# Calculate z-statistic
z_stat = (x_bar - mu_0) / (sigma / np.sqrt(n))
print(f"z = {z_stat:.4f}")

# Two-tailed p-value
p_value = 2 * stats.norm.sf(abs(z_stat))
print(f"p-value = {p_value:.4f}")

# Decision
alpha = 0.05
if p_value < alpha:
    print("Reject H0")
else:
    print("Fail to reject H0")
```

### Critical Values (Common)

| $\alpha$ | Two-tailed $z_{\alpha/2}$ | One-tailed $z_\alpha$ |
|----------|--------------------------|----------------------|
| 0.10 | ±1.645 | 1.282 |
| 0.05 | ±1.960 | 1.645 |
| 0.01 | ±2.576 | 2.326 |

---

## 5.5 T-Test

### When to Use

- Population standard deviation $\sigma$ is **unknown** (use sample $s$ instead)
- Sample size is **small** ($n < 30$) — t-distribution has heavier tails
- Data is approximately normally distributed (important for small $n$)

### T-Distribution

The t-distribution looks like a normal distribution but with **heavier tails** (more probability in the extremes), accounting for the extra uncertainty from estimating $\sigma$ with $s$.

- Parameterized by **degrees of freedom**: $df = n - 1$
- As $df \to \infty$, t-distribution → standard normal
- For $df > 30$, t and z are nearly identical

### Test Statistic

$$t = \frac{\bar{x} - \mu_0}{s / \sqrt{n}}$$

where $s$ is the **sample** standard deviation.

### One-Sample T-Test in Python

```python
from scipy import stats
import numpy as np

sample = np.array([102, 98, 105, 99, 101, 103, 97, 104, 100, 106])
mu_0 = 100

# Method 1: Using scipy.stats.ttest_1samp
t_stat, p_value = stats.ttest_1samp(sample, popmean=mu_0)
print(f"t = {t_stat:.4f}, p = {p_value:.4f}")

# Method 2: Manual calculation
n = len(sample)
x_bar = np.mean(sample)
s = np.std(sample, ddof=1)   # Sample std dev (ddof=1!)
t_manual = (x_bar - mu_0) / (s / np.sqrt(n))
p_manual = 2 * stats.t.sf(abs(t_manual), df=n-1)
print(f"t = {t_manual:.4f}, p = {p_manual:.4f}")
```

### Two-Sample T-Test

```python
group_a = np.array([85, 90, 88, 92, 87])
group_b = np.array([78, 82, 80, 85, 79])

# Independent two-sample t-test (assumes equal variance)
t_stat, p_value = stats.ttest_ind(group_a, group_b)
print(f"t = {t_stat:.4f}, p = {p_value:.4f}")

# Welch's t-test (does NOT assume equal variance) — safer default
t_stat, p_value = stats.ttest_ind(group_a, group_b, equal_var=False)
```

### Z-Test vs. T-Test Decision Guide

| Condition | Use |
|-----------|-----|
| $\sigma$ known, $n \geq 30$ | **Z-test** |
| $\sigma$ known, $n < 30$, normal pop. | **Z-test** |
| $\sigma$ unknown, any $n$ | **T-test** |
| $\sigma$ unknown, $n < 30$ | **T-test** (critical — heavier tails matter) |

**Pitfall:** When $\sigma$ is unknown (the common case in practice), ALWAYS use the t-test. Using z when $\sigma$ is estimated from data underestimates uncertainty.

---

## 5.6 Confidence Intervals

### What is a Confidence Interval?

A **confidence interval (CI)** provides a range of plausible values for a population parameter, along with a confidence level (e.g., 95%).

**Interpretation:** If we repeated the sampling process many times and computed a 95% CI each time, approximately 95% of those intervals would contain the true parameter.

**Pitfall:** A 95% CI does NOT mean "there is a 95% probability the parameter is in this interval." The parameter is fixed; the interval is random.

### CI for Mean — Known $\sigma$ (Z-based)

$$\bar{x} \pm z_{\alpha/2} \cdot \frac{\sigma}{\sqrt{n}}$$

```python
x_bar = 50
sigma = 10
n = 100
alpha = 0.05
z_crit = stats.norm.ppf(1 - alpha/2)  # 1.96

margin = z_crit * sigma / np.sqrt(n)
CI = (x_bar - margin, x_bar + margin)
print(f"95% CI: ({CI[0]:.2f}, {CI[1]:.2f})")
# 95% CI: (48.04, 51.96)
```

### CI for Mean — Unknown $\sigma$ (T-based)

$$\bar{x} \pm t_{\alpha/2, \, df} \cdot \frac{s}{\sqrt{n}}$$

where $df = n - 1$.

```python
sample = np.array([102, 98, 105, 99, 101, 103, 97, 104, 100, 106])
n = len(sample)
x_bar = np.mean(sample)
s = np.std(sample, ddof=1)
alpha = 0.05

t_crit = stats.t.ppf(1 - alpha/2, df=n-1)
margin = t_crit * s / np.sqrt(n)
CI = (x_bar - margin, x_bar + margin)
print(f"95% CI: ({CI[0]:.2f}, {CI[1]:.2f})")

# Or use scipy directly:
CI = stats.t.interval(0.95, df=n-1, loc=x_bar, scale=s/np.sqrt(n))
print(f"95% CI: ({CI[0]:.2f}, {CI[1]:.2f})")
```

### Factors Affecting CI Width

| Factor | Effect on CI Width |
|--------|--------------------|
| ↑ Confidence level (e.g., 99% vs 95%) | **Wider** (more certainty requires wider range) |
| ↑ Sample size $n$ | **Narrower** (more data → more precise) |
| ↑ Variability ($\sigma$ or $s$) | **Wider** (more spread → less precise) |

### Relationship: CI and Hypothesis Testing

A 95% CI and a two-tailed test at $\alpha = 0.05$ give the **same conclusion**: reject $H_0: \mu = \mu_0$ if and only if $\mu_0$ falls outside the 95% CI.

---

## 5.7 Degrees of Freedom

**Degrees of freedom (df)** = the number of independent pieces of information that go into estimating a parameter.

- For one-sample t-test: $df = n - 1$ (one constraint: the sample mean)
- For two-sample t-test (equal var): $df = n_1 + n_2 - 2$
- For Welch's t-test: $df$ is approximated by the Welch–Satterthwaite equation

**Intuition:** When computing sample variance, we use $\bar{x}$ which is computed from the same data. This "uses up" one degree of freedom, leaving $n - 1$ independent deviations.

---
---

# QUICK REFERENCE: Essential scipy.stats Patterns

```python
from scipy import stats
import numpy as np

# --- Distribution objects ---
norm_rv  = stats.norm(loc=0, scale=1)        # Normal(μ=0, σ=1)
binom_rv = stats.binom(n=10, p=0.5)          # Binomial(n=10, p=0.5)
t_rv     = stats.t(df=9)                     # t-distribution, 9 df
expon_rv = stats.expon(scale=1/2)            # Exponential(λ=2)
poisson_rv = stats.poisson(mu=5)             # Poisson(λ=5)

# --- Key methods (work on all distributions) ---
rv.cdf(x)     # P(X ≤ x)
rv.sf(x)      # P(X > x) = 1 - cdf(x)
rv.ppf(q)     # Quantile: x such that P(X ≤ x) = q
rv.rvs(size=n)# Random samples
rv.mean()     # E[X]
rv.var()      # Var(X)

# --- Hypothesis tests ---
stats.ttest_1samp(sample, popmean=μ0)             # One-sample t-test
stats.ttest_ind(sample1, sample2)                  # Two-sample t-test
stats.ttest_ind(sample1, sample2, equal_var=False) # Welch's t-test

# --- Confidence interval ---
stats.t.interval(confidence, df, loc=x_bar, scale=se)
stats.norm.interval(confidence, loc=x_bar, scale=se)
```

---

# FORMULA REFERENCE CARD

| Formula | Expression |
|---------|-----------|
| Sample mean | $\bar{x} = \frac{1}{n}\sum x_i$ |
| Sample variance | $s^2 = \frac{1}{n-1}\sum(x_i - \bar{x})^2$ |
| Standard error | $SE = \frac{s}{\sqrt{n}}$ (or $\frac{\sigma}{\sqrt{n}}$ if $\sigma$ known) |
| Z-score | $z = \frac{x - \mu}{\sigma}$ |
| Z-test statistic | $z = \frac{\bar{x} - \mu_0}{\sigma / \sqrt{n}}$ |
| T-test statistic | $t = \frac{\bar{x} - \mu_0}{s / \sqrt{n}}$ |
| CI (Z-based) | $\bar{x} \pm z_{\alpha/2} \cdot \frac{\sigma}{\sqrt{n}}$ |
| CI (T-based) | $\bar{x} \pm t_{\alpha/2, df} \cdot \frac{s}{\sqrt{n}}$ |
| Binomial PMF | $P(X=k) = \binom{n}{k}p^k(1-p)^{n-k}$ |
| Normal PDF | $f(x) = \frac{1}{\sigma\sqrt{2\pi}}e^{-(x-\mu)^2/(2\sigma^2)}$ |
| Exponential PDF | $f(x) = \lambda e^{-\lambda x}$ |
| Poisson PMF | $P(X=k) = \frac{\lambda^k e^{-\lambda}}{k!}$ |
| CLT | $\bar{X}_n \sim N(\mu, \sigma^2/n)$ for large $n$ |

---

# PITFALLS & EDGE CASES — MASTER LIST

1. **`int("3.5")`** → `ValueError`. Must use `int(float("3.5"))`.
2. **`/` always returns float** in Python 3: `4 / 2 → 2.0`.
3. **Floor division with negatives:** `-7 // 2 → -4` (rounds toward -∞).
4. **Mutable default arguments:** `def f(lst=[])` shares the same list across calls. Use `def f(lst=None)`.
5. **Aliasing:** `b = a` for lists creates a reference, not a copy. Use `.copy()` or `list()`.
6. **`sort()` returns None;** `sorted()` returns a new list.
7. **Empty set:** `set()`, NOT `{}` (that's an empty dict).
8. **Single-element tuple:** `(42,)` not `(42)`.
9. **Set elements must be hashable** — no lists or dicts inside sets.
10. **`np.var()` defaults to ddof=0** (population variance). Use `ddof=1` for sample variance.
11. **scipy exponential:** `scale = 1/λ`, not `λ`.
12. **PDF values can exceed 1** — they are densities, not probabilities.
13. **"Fail to reject H₀" ≠ "Accept H₀."**
14. **P-value is NOT the probability H₀ is true.** It's P(data | H₀).
15. **Statistical significance ≠ practical significance.**
16. **95% CI interpretation:** NOT "95% probability the parameter is in this interval."
17. **Z-test vs T-test:** Use t-test when $\sigma$ is unknown (almost always in practice).
18. **`ttest_1samp` returns a two-tailed p-value.** For one-tailed, divide by 2.
19. **Gambler's Fallacy:** LLN doesn't imply short-run compensation.
20. **Binomial requires independent, identical trials.** Verify assumptions.
