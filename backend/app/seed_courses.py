"""Default course catalog — idempotent, safe to run in every environment
including production (unlike seed_demo_data, which is gated off there).

Seeds platform-authored courses (instructor_id=None — "nobody owns this,
only system.manage can edit it", matching the ownership checks in
app/dependencies.py::require_course_ownership) so every deployment ships
with a real, correct, non-placeholder curriculum instead of an empty catalog.

Content here is deliberately conservative: standard, decades-stable
definitions and algorithms (Big-O, binary search, matrix multiplication,
normal forms, etc.) rather than anything time-sensitive or contested, to
minimize the risk of stating something wrong. Courses form linear
beginner -> intermediate -> advanced chains via Course.prerequisite_course_id
(a single FK, so this models a chain per track, not a full prerequisite DAG —
softer cross-track recommendations are called out in each course's
description instead).

Usage: called from app.seed.main() and from the app startup lifespan,
exactly like seed_rbac() — see app/main.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms import Course, CourseSection, Lesson

# Arbitrary fixed key for the advisory lock in seed_default_courses(). Any
# int64 works as long as it's not reused for an unrelated lock elsewhere.
_SEED_LOCK_KEY = 8_217_460_311_902


@dataclass
class LessonSpec:
    title: str
    content_body: str
    duration_minutes: int = 10
    content_type: str = "article"


@dataclass
class SectionSpec:
    title: str
    lessons: list[LessonSpec]


@dataclass
class CourseSpec:
    slug: str
    title: str
    description: str
    difficulty: str  # beginner | intermediate | advanced
    estimated_hours: int
    skills: list[str]
    specialization: str
    prerequisite_slug: str | None
    sections: list[SectionSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Python Programming I: Foundations
# ---------------------------------------------------------------------------
PYTHON_I = CourseSpec(
    slug="python-programming-i-foundations",
    title="Python Programming I: Foundations",
    description=(
        "A first course in programming using Python. Starts from zero — no prior coding "
        "experience assumed — and covers the core language: variables, control flow, "
        "functions, and the built-in data types you'll use in every program you ever write. "
        "By the end you can read and write straightforward Python scripts and you have the "
        "vocabulary to keep learning."
    ),
    difficulty="beginner",
    estimated_hours=10,
    skills=["Python", "Programming Fundamentals", "Debugging"],
    specialization="Software Development",
    prerequisite_slug=None,
    sections=[
        SectionSpec("Getting Started", [
            LessonSpec(
                "What Is Python, and Why Learn It?",
                "Python is a high-level, general-purpose programming language created by Guido "
                "van Rossum and first released in 1991. \"High-level\" means Python handles "
                "memory management and low-level detail for you, so you write instructions "
                "close to how you'd describe a problem in plain English rather than in terms "
                "the processor understands directly. Python is interpreted, not compiled to a "
                "standalone executable: the `python` interpreter reads your source file and "
                "executes it line by line (in practice it first compiles to bytecode for the "
                "CPython virtual machine, but there's no separate manual compile step you run "
                "yourself). It's dynamically typed (a variable's type is determined by the "
                "value it currently holds, and can change) and famous for readable syntax that "
                "uses indentation, not braces, to mark blocks of code. Python is used across "
                "web backends, data analysis, scientific computing, automation/scripting, and "
                "as a first teaching language precisely because its syntax gets out of the way "
                "of the underlying programming concepts.",
                8,
            ),
            LessonSpec(
                "Setting Up and Running Your First Program",
                "Every Python installation ships an interactive interpreter (the REPL — "
                "Read-Eval-Print Loop) you start by typing `python` or `python3` in a "
                "terminal; it evaluates one expression at a time and prints the result "
                "immediately, which makes it excellent for quick experiments. For real "
                "programs you write source code in a `.py` file and run it with "
                "`python filename.py`. The traditional first program is:\n\n"
                "    print(\"Hello, World!\")\n\n"
                "`print` is a built-in function: it takes the value inside the parentheses "
                "and writes it to standard output (usually your terminal). Text wrapped in "
                "quotes, like \"Hello, World!\", is a string. Get comfortable running both "
                "the REPL and `.py` files before moving on — you'll use both constantly.",
                7,
            ),
        ]),
        SectionSpec("Variables, Types, and Operators", [
            LessonSpec(
                "Variables and Python's Core Data Types",
                "A variable is a name bound to a value: `age = 20` creates the name `age` and "
                "binds it to the integer 20. Python has no variable-declaration keyword — "
                "assignment itself creates the name, and it's dynamically typed, so the same "
                "name can be rebound to a value of a different type later (this is legal, "
                "though not always good style). Python's core built-in types: `int` (whole "
                "numbers, arbitrary precision — Python integers don't overflow), `float` "
                "(numbers with a decimal point, IEEE 754 double precision), `str` (text, "
                "written in single or double quotes), `bool` (`True` or `False`), and "
                "`NoneType` (the single value `None`, representing \"no value\"). Use the "
                "built-in `type()` function to check what type a value is at any time, e.g. "
                "`type(3.14)` returns `<class 'float'>`.",
                10,
            ),
            LessonSpec(
                "Arithmetic, Comparison, and Logical Operators",
                "Arithmetic operators: `+` `-` `*` `/` (true division, always returns a "
                "float) `//` (floor division, discards the remainder) `%` (modulo, the "
                "remainder) `**` (exponentiation). Comparison operators (`==` `!=` `<` `>` "
                "`<=` `>=`) return a `bool`. Note `==` checks equality of value; `is` checks "
                "whether two names refer to the exact same object in memory — these are not "
                "interchangeable, and using `is` to compare values (e.g. `x is 5`) is a common "
                "beginner mistake. Logical operators `and`, `or`, `not` combine boolean "
                "expressions using short-circuit evaluation: in `a and b`, if `a` is falsy, "
                "`b` is never evaluated at all.",
                9,
            ),
            LessonSpec(
                "Strings: Creation, Indexing, and Formatting",
                "Strings are immutable sequences of characters. Index with square brackets, "
                "zero-based: `s[0]` is the first character, `s[-1]` the last. Slicing "
                "`s[start:stop]` returns a substring from `start` up to (not including) "
                "`stop`. Because strings are immutable, `s[0] = 'X'` raises a `TypeError` — "
                "string methods like `.upper()`, `.replace()`, `.split()`, and `.strip()` all "
                "return a *new* string rather than modifying the original. The modern way to "
                "build a string from variables is an f-string: `f\"{name} is {age} years "
                "old\"` evaluates the expressions inside `{}` and substitutes them directly.",
                10,
            ),
        ]),
        SectionSpec("Control Flow", [
            LessonSpec(
                "Conditionals: if / elif / else",
                "Python's `if` statement executes a block only when a condition is truthy. "
                "`elif` (else-if) chains additional conditions, and `else` catches everything "
                "not matched above. Unlike many languages, Python has no `switch` statement in "
                "older versions (3.10+ added `match`/`case` as a structural pattern-matching "
                "alternative) — a chain of `elif` is the traditional idiom. Blocks are defined "
                "purely by indentation (conventionally 4 spaces); there are no curly braces, "
                "and mixing tabs and spaces inconsistently will raise an `IndentationError`. "
                "Truthiness: besides `False`, the values `0`, `0.0`, `\"\"` (empty string), "
                "`[]` (empty list), `{}` (empty dict), and `None` are all falsy — everything "
                "else is truthy.",
                9,
            ),
            LessonSpec(
                "Loops: for and while",
                "A `for` loop in Python iterates over the items of any *iterable* (a "
                "sequence like a list or string, or anything implementing the iterator "
                "protocol) — it is fundamentally different from a C-style counting loop. To "
                "loop a fixed number of times, iterate over `range(n)`, which lazily "
                "produces 0, 1, ..., n-1. A `while` loop repeats as long as its condition "
                "stays truthy, and is the right choice when you don't know the number of "
                "iterations in advance. `break` exits the nearest enclosing loop immediately; "
                "`continue` skips to the next iteration. A `for`/`while` loop can also have "
                "an `else` clause, which runs only if the loop completed without hitting a "
                "`break` — a lesser-known but occasionally very useful feature.",
                10,
            ),
        ]),
        SectionSpec("Functions and Basic Data Structures", [
            LessonSpec(
                "Defining and Calling Functions",
                "Define a function with `def name(parameters):` followed by an indented "
                "body; `return` sends a value back to the caller (a function with no explicit "
                "`return` implicitly returns `None`). Parameters can have default values "
                "(`def greet(name, greeting=\"Hello\")`), and callers can pass arguments "
                "positionally or by keyword (`greet(name=\"Ana\")`). Functions are first-class "
                "objects in Python — you can assign a function to a variable, pass it as an "
                "argument to another function, or return it from a function, which underlies "
                "patterns like callbacks and decorators covered later. A function's docstring "
                "(a string literal as the first statement in its body) documents what it does "
                "and is accessible via `help(function_name)`.",
                10,
            ),
            LessonSpec(
                "Lists, Tuples, and Dictionaries",
                "A `list` (`[1, 2, 3]`) is an ordered, mutable sequence — append with "
                "`.append()`, remove with `.remove()` or `del`, index and slice just like "
                "strings. A `tuple` (`(1, 2, 3)`) is ordered but immutable — commonly used for "
                "fixed collections like coordinate pairs, and because they're immutable and "
                "hashable, tuples of hashable values can be used as dictionary keys where "
                "lists cannot. A `dict` (`{\"a\": 1, \"b\": 2}`) maps keys to values with "
                "average O(1) lookup, insertion, and deletion (backed by a hash table); as of "
                "Python 3.7, dicts preserve insertion order as a language guarantee, not just "
                "an implementation detail. All three support `len()` to get their size, and "
                "`in` to test membership.",
                12,
            ),
        ]),
    ],
)

# ---------------------------------------------------------------------------
# Python Programming II: Intermediate — OOP, Files, and the Standard Library
# ---------------------------------------------------------------------------
PYTHON_II = CourseSpec(
    slug="python-programming-ii-intermediate",
    title="Python Programming II: Intermediate",
    description=(
        "Builds on Python I: object-oriented programming, exception handling, file I/O, "
        "and a tour of the standard-library tools every real Python program ends up using. "
        "This is the course that turns you from someone who can write a script into someone "
        "who can structure a real, maintainable program."
    ),
    difficulty="intermediate",
    estimated_hours=10,
    skills=["Python", "Object-Oriented Programming", "Error Handling", "File I/O"],
    specialization="Software Development",
    prerequisite_slug="python-programming-i-foundations",
    sections=[
        SectionSpec("Object-Oriented Programming", [
            LessonSpec(
                "Classes, Objects, and __init__",
                "A class is a blueprint for creating objects that bundle data (attributes) "
                "and behavior (methods) together. Define one with `class ClassName:`; the "
                "special method `__init__(self, ...)` runs automatically when you create a "
                "new instance (`ClassName(...)`) and is where you set up instance attributes "
                "via `self.attribute = value`. `self` refers to the specific instance the "
                "method is being called on and must be the first parameter of every instance "
                "method by convention — Python passes it automatically when you call "
                "`instance.method()`. An object created from a class is called an instance; "
                "you can create as many independent instances of one class as you need, each "
                "with its own attribute values.",
                11,
            ),
            LessonSpec(
                "Inheritance and Method Overriding",
                "A class can inherit from another: `class Dog(Animal):` makes `Dog` a "
                "subclass of `Animal`, gaining all of `Animal`'s methods and attributes. A "
                "subclass can override a method by redefining it with the same name, and can "
                "call the parent's version explicitly with `super().method_name()` — most "
                "commonly `super().__init__(...)` inside a subclass's own `__init__` to run "
                "the parent's setup logic before adding its own. Python supports multiple "
                "inheritance (a class can inherit from more than one parent), which Java and "
                "C# deliberately don't, resolved via the C3 linearization algorithm (the "
                "\"method resolution order\", inspectable via `ClassName.__mro__`).",
                10,
            ),
        ]),
        SectionSpec("Errors and Robust Code", [
            LessonSpec(
                "Exceptions: try, except, finally",
                "Python signals errors by raising exceptions rather than returning error "
                "codes. Wrap risky code in a `try` block; `except ExceptionType:` catches a "
                "specific exception type and its subclasses (catching bare `except:` with no "
                "type is almost always a mistake — it silently swallows things like "
                "`KeyboardInterrupt` too). `finally` runs whether or not an exception "
                "occurred, and is the right place for cleanup that must always happen (e.g. "
                "closing a file). You can raise your own exceptions with `raise ValueError"
                "(\"message\")`, and define custom exception types by subclassing `Exception`. "
                "The general principle in Python (\"EAFP\" — Easier to Ask Forgiveness than "
                "Permission) favors trying an operation and catching the exception over "
                "checking preconditions first.",
                10,
            ),
        ]),
        SectionSpec("Working with Files and the Standard Library", [
            LessonSpec(
                "Reading and Writing Files",
                "Open a file with the built-in `open(path, mode)`, where mode is `'r'` (read, "
                "default), `'w'` (write, truncates existing content), `'a'` (append), or add "
                "`'b'` for binary. Always use a `with` statement — `with open(path) as f:` — "
                "which guarantees the file is closed automatically when the block exits, even "
                "if an exception occurs inside it; this is the same context-manager protocol "
                "used elsewhere in the standard library (database connections, locks). "
                "`f.read()` reads the whole file as a string; iterating over `f` directly "
                "(`for line in f:`) reads it lazily, one line at a time, which matters for "
                "large files that shouldn't be loaded fully into memory.",
                9,
            ),
            LessonSpec(
                "A Tour of Useful Standard-Library Modules",
                "Python ships with a large standard library — \"batteries included\" is the "
                "project's own description. Some modules you'll reach for constantly: `json` "
                "(parse/serialize JSON, the de facto data-interchange format for web APIs), "
                "`datetime` (dates and times), `os` and `pathlib` (filesystem paths and "
                "operations — `pathlib.Path` is the modern, object-oriented way to handle "
                "paths), `collections` (specialized containers like `Counter` and "
                "`defaultdict`), `re` (regular expressions for pattern matching in text), and "
                "`itertools` (efficient, memory-conscious iteration tools). Knowing what's "
                "already in the standard library — and reaching for it before writing your "
                "own version or reaching for a third-party package — is a real productivity "
                "skill.",
                10,
            ),
        ]),
    ],
)

# ---------------------------------------------------------------------------
# SQL & Relational Databases
# ---------------------------------------------------------------------------
SQL = CourseSpec(
    slug="sql-and-relational-databases",
    title="SQL & Relational Databases",
    description=(
        "How relational databases actually work, and how to query them with SQL: tables, "
        "keys, joins, aggregation, and the normalization rules that keep data consistent. "
        "This is the foundation for Data Engineering and for backend development generally — "
        "almost every real application talks to a relational database somewhere."
    ),
    difficulty="beginner",
    estimated_hours=8,
    skills=["SQL", "Relational Databases", "Data Modeling"],
    specialization="Data",
    prerequisite_slug=None,
    sections=[
        SectionSpec("Relational Model Basics", [
            LessonSpec(
                "Tables, Rows, and Keys",
                "A relational database organizes data into tables (also called relations), "
                "each with a fixed set of named, typed columns and any number of rows. A "
                "primary key is one column (or a combination of columns) whose value "
                "uniquely identifies each row in the table — no two rows may share one, and "
                "it cannot be NULL. A foreign key is a column in one table that references "
                "the primary key of another table, which is how relational databases model "
                "relationships between entities (e.g. an `orders` table's `customer_id` "
                "column references `customers.id`) while enforcing referential integrity: the "
                "database refuses to insert an order for a customer that doesn't exist, or "
                "(depending on the constraint) to delete a customer who still has orders.",
                9,
            ),
            LessonSpec(
                "SELECT, WHERE, and Sorting Results",
                "The basic query shape is `SELECT columns FROM table WHERE condition "
                "ORDER BY column;`. `SELECT *` returns every column, but naming the columns "
                "you actually need is better practice — it's explicit and doesn't break if "
                "the table gains new columns later. `WHERE` filters rows using comparison "
                "operators (`=`, `<>` or `!=`, `<`, `>`), logical combinators (`AND`, `OR`, "
                "`NOT`), `LIKE` for pattern matching with `%` (any characters) and `_` (one "
                "character) wildcards, `IN (...)` for matching a value against a list, and "
                "`IS NULL` / `IS NOT NULL` (note: `= NULL` is never true in SQL — NULL "
                "represents an unknown value, so it can't be equal to anything, including "
                "another NULL). `ORDER BY column DESC` sorts descending; the default is "
                "ascending.",
                10,
            ),
        ]),
        SectionSpec("Combining and Aggregating Data", [
            LessonSpec(
                "JOINs: Combining Rows Across Tables",
                "An `INNER JOIN` (the default when you write plain `JOIN`) returns only rows "
                "that have a match in both tables: `SELECT * FROM orders JOIN customers ON "
                "orders.customer_id = customers.id`. A `LEFT JOIN` returns every row from the "
                "left table regardless of whether it has a match on the right — unmatched "
                "columns from the right table come back as NULL, which is the standard way to "
                "answer \"show me all X, including ones with no matching Y\" (e.g. all "
                "customers, including those with zero orders). A `RIGHT JOIN` is the mirror "
                "image, and a `FULL OUTER JOIN` keeps unmatched rows from both sides — not "
                "every database engine supports `FULL OUTER JOIN` natively (notably, older "
                "MySQL versions don't).",
                11,
            ),
            LessonSpec(
                "GROUP BY and Aggregate Functions",
                "Aggregate functions — `COUNT()`, `SUM()`, `AVG()`, `MIN()`, `MAX()` — "
                "collapse multiple rows into a single summary value. `GROUP BY column` "
                "partitions rows into groups sharing the same value in that column and "
                "applies the aggregate function separately within each group, e.g. "
                "`SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id` gives one "
                "row per customer with their order count. `HAVING` filters groups *after* "
                "aggregation (e.g. `HAVING COUNT(*) > 5`), which is why it's needed at all — "
                "`WHERE` filters individual rows before grouping happens, so it can't "
                "reference an aggregate result.",
                10,
            ),
        ]),
        SectionSpec("Designing Correct Schemas", [
            LessonSpec(
                "Normalization: Why and How",
                "Normalization is the process of structuring tables to reduce data "
                "redundancy and prevent update anomalies (situations where the same fact is "
                "stored in multiple places and can go out of sync). First Normal Form (1NF) "
                "requires atomic column values — no repeating groups or arrays crammed into "
                "one column. Second Normal Form (2NF) requires 1NF plus that every non-key "
                "column depends on the *whole* primary key, not just part of it (relevant "
                "for composite keys). Third Normal Form (3NF) requires 2NF plus that no "
                "non-key column depends on another non-key column (no \"transitive\" "
                "dependencies) — e.g. storing both `customer_id` and `customer_city` on an "
                "orders table is a 3NF violation, because city depends on the customer, not "
                "directly on the order. In practice, most production schemas are designed to "
                "3NF and then deliberately, selectively denormalized for performance where "
                "measured and justified.",
                12,
            ),
            LessonSpec(
                "Indexes and Why Queries Get Slow",
                "Without an index, finding rows that match a `WHERE` condition requires "
                "scanning every row in the table (a \"sequential scan\" or \"full table "
                "scan\") — fine for a few hundred rows, ruinous for millions. An index is an "
                "auxiliary data structure (commonly a B-tree) built on one or more columns "
                "that lets the database jump directly to matching rows instead of scanning "
                "everything, at the cost of extra storage and slightly slower writes (the "
                "index has to be updated too). Primary keys are indexed automatically; "
                "columns you frequently filter or join on are good index candidates. Indexing "
                "every column \"just in case\" is a common beginner mistake — each index adds "
                "real write overhead, so indexes should be added deliberately, based on the "
                "queries the application actually runs.",
                10,
            ),
        ]),
    ],
)

# ---------------------------------------------------------------------------
# Linear Algebra for Computing
# ---------------------------------------------------------------------------
LINEAR_ALGEBRA = CourseSpec(
    slug="linear-algebra-for-computing",
    title="Linear Algebra for Computing",
    description=(
        "The linear algebra that shows up everywhere in computing: vectors, matrices, "
        "linear systems, determinants, and eigenvalues. No prior linear algebra assumed — "
        "just comfort with basic algebra. This is foundational for machine learning, "
        "computer graphics, and numerical computing generally."
    ),
    difficulty="beginner",
    estimated_hours=9,
    skills=["Linear Algebra", "Vectors", "Matrices", "Mathematical Reasoning"],
    specialization="Mathematics",
    prerequisite_slug=None,
    sections=[
        SectionSpec("Vectors", [
            LessonSpec(
                "Vectors: Definition and Basic Operations",
                "A vector in n-dimensional space is an ordered list of n real numbers, "
                "written as a column: v = (v1, v2, ..., vn). Geometrically, a vector "
                "represents both a magnitude and a direction, often visualized as an arrow "
                "from the origin to the point (v1, ..., vn). Vector addition is componentwise: "
                "(a1, a2) + (b1, b2) = (a1+b1, a2+b2). Scalar multiplication scales every "
                "component by the same number: c * (v1, v2) = (c*v1, c*v2). These two "
                "operations — addition and scalar multiplication — are what make a vector "
                "space a vector space, and every other operation in linear algebra is built "
                "on top of them.",
                9,
            ),
            LessonSpec(
                "Dot Product, Length, and Angle",
                "The dot product of two vectors of the same dimension is the sum of the "
                "products of their corresponding components: a . b = a1*b1 + a2*b2 + ... + "
                "an*bn. The dot product of a vector with itself gives the square of its "
                "length: |v|^2 = v . v, so |v| = sqrt(v . v) (this is just the Pythagorean "
                "theorem generalized to n dimensions). The dot product also relates to the "
                "angle theta between two vectors via a . b = |a| |b| cos(theta) — in "
                "particular, two nonzero vectors are perpendicular (orthogonal) exactly when "
                "their dot product is zero. This connection between an easy-to-compute "
                "algebraic quantity (the dot product) and a geometric one (the angle) is used "
                "constantly, e.g. to measure similarity between vectors in machine learning "
                "(cosine similarity).",
                10,
            ),
        ]),
        SectionSpec("Matrices", [
            LessonSpec(
                "Matrices and Matrix Multiplication",
                "A matrix is a rectangular array of numbers with m rows and n columns (an "
                "\"m by n\" matrix). Matrix addition and scalar multiplication work "
                "componentwise, same as vectors. Matrix multiplication is different and "
                "less obvious: to multiply an m x n matrix A by an n x p matrix B, the "
                "number of columns of A must equal the number of rows of B, and the entry in "
                "row i, column j of the product is the dot product of row i of A with column "
                "j of B. Matrix multiplication is NOT commutative in general — A*B usually "
                "does not equal B*A, and B*A may not even be defined if the dimensions don't "
                "line up the other way. A useful way to think about it: multiplying a vector "
                "by a matrix is a linear transformation — it rotates, scales, or shears the "
                "vector, and matrix multiplication is composing two transformations.",
                12,
            ),
            LessonSpec(
                "The Identity Matrix and Matrix Inverses",
                "The n x n identity matrix I has 1s on the main diagonal and 0s everywhere "
                "else; multiplying any matrix by the identity (on the compatible side) "
                "leaves it unchanged, the matrix equivalent of multiplying a number by 1. A "
                "square matrix A has an inverse A^-1 if A * A^-1 = A^-1 * A = I; not every "
                "square matrix has one (a matrix without an inverse is called singular). "
                "Inverses are used to solve linear systems: if Ax = b and A is invertible, "
                "then x = A^-1 * b. In practice, numerically computing an explicit inverse is "
                "rarely how systems are actually solved in software — methods like Gaussian "
                "elimination or LU decomposition are more numerically stable and efficient — "
                "but the inverse is the right conceptual tool for understanding what solving "
                "the system means.",
                11,
            ),
        ]),
        SectionSpec("Systems, Determinants, and Eigenvalues", [
            LessonSpec(
                "Solving Linear Systems with Gaussian Elimination",
                "A system of linear equations can be written as a matrix equation Ax = b. "
                "Gaussian elimination solves it by using row operations — swapping two rows, "
                "multiplying a row by a nonzero constant, or adding a multiple of one row to "
                "another — to transform the augmented matrix [A | b] into row-echelon form "
                "(a triangular shape with zeros below the leading entry of each row), from "
                "which the solution can be read off directly by back-substitution. A system "
                "can have exactly one solution, no solution (an inconsistent system, "
                "revealed by a row like [0 0 0 | 5] during elimination), or infinitely many "
                "solutions (when the system is under-determined). These row operations are "
                "the basis of how software actually solves linear systems numerically.",
                11,
            ),
            LessonSpec(
                "Determinants and Eigenvalues",
                "The determinant of a square matrix is a single number that encodes several "
                "important facts about it: a matrix is invertible if and only if its "
                "determinant is nonzero, and the absolute value of the determinant is the "
                "factor by which the matrix scales area (in 2D) or volume (in 3D) under its "
                "linear transformation. An eigenvector of a matrix A is a nonzero vector v "
                "such that Av = lambda*v for some scalar lambda (the corresponding "
                "eigenvalue) — that is, the transformation only stretches or shrinks v, "
                "without rotating it off its own line. Eigenvalues are found as the roots of "
                "the characteristic polynomial det(A - lambda*I) = 0. Eigenvalues and "
                "eigenvectors are central to techniques like Principal Component Analysis "
                "and to understanding the long-run behavior of systems that repeatedly apply "
                "the same linear transformation.",
                12,
            ),
        ]),
    ],
)

# ---------------------------------------------------------------------------
# Data Structures & Algorithms (intermediate) and Algorithms & Complexity (advanced)
# ---------------------------------------------------------------------------
DSA = CourseSpec(
    slug="data-structures-and-algorithms",
    title="Data Structures & Algorithms",
    description=(
        "The data structures every programmer needs — arrays, linked lists, stacks, queues, "
        "trees, and hash tables — and how to reason about the time and space they cost. "
        "This is the course that turns 'my code works' into 'my code works and won't fall "
        "over at scale.'"
    ),
    difficulty="intermediate",
    estimated_hours=12,
    skills=["Data Structures", "Algorithm Analysis", "Python"],
    specialization="Computer Science",
    prerequisite_slug="python-programming-ii-intermediate",
    sections=[
        SectionSpec("Measuring Efficiency", [
            LessonSpec(
                "Big-O Notation",
                "Big-O notation describes how an algorithm's running time (or memory use) "
                "grows as the input size n grows, ignoring constant factors and lower-order "
                "terms — it answers \"how does this scale?\", not \"how many milliseconds "
                "does this take on my laptop?\". Common complexities, from fastest-growing to "
                "slowest: O(1) constant (independent of n, e.g. array index access), O(log n) "
                "logarithmic (e.g. binary search — each step halves the remaining "
                "possibilities), O(n) linear (e.g. scanning a list once), O(n log n) "
                "\"linearithmic\" (e.g. efficient sorting algorithms like mergesort), O(n^2) "
                "quadratic (e.g. comparing every pair of elements, or simple sorts like "
                "bubble sort), and O(2^n) exponential (e.g. naive recursive solutions that "
                "recompute overlapping subproblems). Big-O is specifically an upper bound on "
                "worst-case growth; Big-Omega describes a lower bound, and Big-Theta describes "
                "a tight bound where both match.",
                11,
            ),
        ]),
        SectionSpec("Linear Structures", [
            LessonSpec(
                "Arrays and Linked Lists",
                "An array stores elements in contiguous memory, giving O(1) random access by "
                "index (the address of element i is computable directly from the base "
                "address and i) but O(n) insertion or deletion in the middle, since every "
                "following element has to shift. A linked list stores elements as separate "
                "nodes, each holding a value and a reference (pointer) to the next node; "
                "insertion or deletion at a known position is O(1) once you're there (just "
                "rewire two pointers), but there's no random access — reaching the k-th "
                "element requires walking k links from the head, so lookup is O(n). A doubly "
                "linked list adds a `previous` pointer to each node too, allowing O(1) "
                "removal of a node you already hold a reference to, and traversal in either "
                "direction.",
                11,
            ),
            LessonSpec(
                "Stacks and Queues",
                "A stack is a Last-In-First-Out (LIFO) structure: `push` adds to the top, "
                "`pop` removes from the top — the most recently added element is always the "
                "first one removed. Stacks are the natural structure for anything with nested "
                "or reversible structure: function call frames (the \"call stack\"), "
                "undo/redo history, and matching balanced parentheses. A queue is First-In-"
                "First-Out (FIFO): `enqueue` adds to the back, `dequeue` removes from the "
                "front — used for processing things in the order they arrived, like a task "
                "queue or breadth-first search's frontier. Both operations are O(1) with an "
                "appropriate underlying implementation (a linked list, or an array used as a "
                "circular buffer for the queue case).",
                10,
            ),
        ]),
        SectionSpec("Trees and Hash Tables", [
            LessonSpec(
                "Binary Search Trees",
                "A binary search tree (BST) is a binary tree where, for every node, all "
                "values in its left subtree are smaller and all values in its right subtree "
                "are larger. This ordering property means search, insertion, and deletion all "
                "take O(log n) time on a *balanced* tree of height log n — but a BST built by "
                "inserting already-sorted data degenerates into a straight line (effectively "
                "a linked list), giving O(n) worst-case for all three operations. This is "
                "exactly why self-balancing variants exist — AVL trees and red-black trees "
                "both add extra rules and rebalancing operations during insertion/deletion to "
                "guarantee O(log n) height no matter the insertion order; red-black trees are "
                "what underlie many standard-library ordered map/set implementations, "
                "including C++'s `std::map` and Java's `TreeMap`.",
                12,
            ),
            LessonSpec(
                "Hash Tables",
                "A hash table maps keys to values by applying a hash function to the key to "
                "compute an array index, giving average-case O(1) lookup, insertion, and "
                "deletion — dramatically faster than a linear scan for large collections. "
                "When two different keys hash to the same index (a collision — inevitable "
                "once you have more possible keys than array slots, by the pigeonhole "
                "principle), the two most common resolution strategies are chaining (each "
                "array slot holds a small list of all entries that hashed there) and open "
                "addressing (on a collision, probe forward to the next open slot using some "
                "fixed rule). A good hash function distributes keys roughly uniformly across "
                "the table; a bad one clusters many keys into few slots, degrading toward "
                "O(n) worst-case lookup. Python's `dict` and `set`, and this course's own "
                "`Question`/database indexing concepts, both rely on hash tables under the "
                "hood.",
                12,
            ),
        ]),
    ],
)

ALGORITHMS = CourseSpec(
    slug="algorithms-and-complexity-analysis",
    title="Algorithms & Complexity Analysis",
    description=(
        "Classic algorithmic techniques and how to prove they're correct and fast: sorting, "
        "searching, recursion, divide-and-conquer, and an introduction to dynamic "
        "programming and graph algorithms. Assumes comfort with the data structures from the "
        "prerequisite course."
    ),
    difficulty="advanced",
    estimated_hours=14,
    skills=["Algorithms", "Dynamic Programming", "Graph Theory", "Recursion"],
    specialization="Computer Science",
    prerequisite_slug="data-structures-and-algorithms",
    sections=[
        SectionSpec("Sorting and Searching", [
            LessonSpec(
                "Comparison Sorting: Mergesort and Quicksort",
                "Mergesort is a divide-and-conquer algorithm: split the array in half, "
                "recursively sort each half, then merge the two sorted halves in linear "
                "time. It always runs in O(n log n) time (there are log n levels of "
                "splitting, and merging at each level touches every element once, so O(n) "
                "per level) and is stable (equal elements keep their relative order), at the "
                "cost of O(n) extra space for the merge step. Quicksort picks a pivot "
                "element, partitions the array into elements less than and greater than the "
                "pivot, and recursively sorts each side; average case is also O(n log n) and "
                "it sorts in place (O(log n) extra space for recursion), but a poor pivot "
                "choice on already-sorted or adversarial input degrades it to O(n^2) worst "
                "case — real implementations mitigate this with randomized or median-of-"
                "three pivot selection. It is a mathematical fact (proven via a decision-tree "
                "argument) that no comparison-based sort can do better than O(n log n) in "
                "the worst case.",
                13,
            ),
            LessonSpec(
                "Binary Search",
                "Binary search finds a target value in a *sorted* array in O(log n) time by "
                "repeatedly comparing the target to the middle element and discarding the "
                "half of the array that can't contain it. Each comparison halves the search "
                "space, so after k steps at most n / 2^k elements remain — the algorithm "
                "terminates after O(log n) steps. Binary search requires the input to be "
                "sorted; running it on unsorted data gives no correctness guarantee at all. "
                "The technique generalizes beyond literal array search to any monotonic "
                "predicate — \"binary search on the answer\" is a common competitive-"
                "programming pattern for optimization problems where you can cheaply check "
                "\"is answer X feasible?\" and feasibility is monotonic in X.",
                9,
            ),
        ]),
        SectionSpec("Recursion and Dynamic Programming", [
            LessonSpec(
                "Recursion and Recurrence Relations",
                "A recursive function calls itself on a smaller version of the same problem, "
                "and must have at least one base case that terminates the recursion directly "
                "without a further recursive call — omitting one causes infinite recursion "
                "(in practice, a stack overflow). The running time of a recursive algorithm "
                "is often expressed as a recurrence relation, e.g. mergesort's T(n) = 2*T(n/2) "
                "+ O(n) (two recursive calls on half the input, plus linear work to merge), "
                "which the Master Theorem resolves to T(n) = O(n log n). Every recursive "
                "algorithm can be rewritten iteratively using an explicit stack, and "
                "sometimes must be for performance — Python, notably, does not perform tail-"
                "call optimization, so deep recursion in Python can hit `RecursionError` well "
                "before it would be a problem in a language that does optimize tail calls.",
                11,
            ),
            LessonSpec(
                "Dynamic Programming: Memoization and Tabulation",
                "Dynamic programming solves problems that have overlapping subproblems (the "
                "same subproblem recurs many times in a naive recursive solution) and optimal "
                "substructure (an optimal solution can be built from optimal solutions to "
                "subproblems) by computing each distinct subproblem's answer exactly once and "
                "reusing it. Memoization is the top-down version: write the natural recursive "
                "solution, but cache each subproblem's result the first time it's computed "
                "(e.g. with a dictionary or `functools.lru_cache` in Python) so repeat calls "
                "return instantly. Tabulation is the bottom-up version: build a table of "
                "subproblem answers iteratively, smallest first, so each larger subproblem "
                "can look up the smaller answers it depends on. The canonical illustrative "
                "example is Fibonacci: naive recursion is O(2^n) because it recomputes the "
                "same values repeatedly; memoized or tabulated, it's O(n).",
                13,
            ),
        ]),
        SectionSpec("Graph Algorithms", [
            LessonSpec(
                "Graph Representations and Traversal (BFS/DFS)",
                "A graph is a set of vertices (nodes) connected by edges, and can be directed "
                "(edges have a direction) or undirected, weighted or unweighted. Two common "
                "representations: an adjacency list (each vertex stores a list of its "
                "neighbors — space-efficient for sparse graphs, O(V + E) total space) and an "
                "adjacency matrix (a V x V grid where entry [i][j] indicates an edge from i to "
                "j — O(1) edge-existence checks but O(V^2) space regardless of how many edges "
                "actually exist). Breadth-first search (BFS) explores level by level using a "
                "queue, and is the right tool for finding the shortest path in an unweighted "
                "graph. Depth-first search (DFS) explores as far as possible down each branch "
                "before backtracking, typically implemented with a stack or recursion, and is "
                "the basis for cycle detection and topological sorting. Both visit every "
                "vertex and edge once, so both run in O(V + E) time.",
                13,
            ),
            LessonSpec(
                "Shortest Paths: Dijkstra's Algorithm",
                "Dijkstra's algorithm finds the shortest path from a single source vertex to "
                "every other vertex in a weighted graph with non-negative edge weights. It "
                "maintains a set of vertices whose shortest distance from the source is "
                "already finalized, and repeatedly picks the unfinalized vertex with the "
                "smallest tentative distance (efficiently, using a min-priority-queue/heap), "
                "finalizes it, and relaxes (updates) the tentative distances of its "
                "neighbors. Using a binary heap for the priority queue, this runs in "
                "O((V + E) log V) time. The algorithm's core assumption — non-negative "
                "weights — is essential to its greedy correctness argument; graphs with "
                "negative edge weights require a different algorithm (Bellman-Ford, which "
                "also detects negative cycles, at the cost of slower O(V*E) running time).",
                12,
            ),
        ]),
    ],
)

# ---------------------------------------------------------------------------
# Data Engineering Foundations
# ---------------------------------------------------------------------------
DATA_ENGINEERING = CourseSpec(
    slug="data-engineering-foundations",
    title="Data Engineering Foundations",
    description=(
        "How data actually moves and gets shaped in a real organization: ETL/ELT pipelines, "
        "data warehouses versus data lakes, batch versus streaming processing, and the "
        "modeling patterns (star schemas, slowly changing dimensions) that make analytics "
        "queries fast and correct. Builds directly on SQL & Relational Databases; comfort "
        "with Python is strongly recommended for the pipeline examples."
    ),
    difficulty="intermediate",
    estimated_hours=11,
    skills=["Data Engineering", "ETL", "Data Warehousing", "SQL"],
    specialization="Data",
    prerequisite_slug="sql-and-relational-databases",
    sections=[
        SectionSpec("The Data Engineering Landscape", [
            LessonSpec(
                "What Data Engineers Actually Build",
                "Data engineering is the discipline of building the systems that reliably "
                "move data from where it's generated (application databases, event logs, "
                "third-party APIs) to where it's needed for analytics, reporting, and machine "
                "learning. A data engineer's core deliverable is usually a pipeline: a series "
                "of steps that extracts data from a source, transforms it into a clean and "
                "consistent shape, and loads it into a destination system optimized for the "
                "consumers who'll query it. This is distinct from software engineering (which "
                "builds the applications that produce the data in the first place) and from "
                "data science/analytics (which consumes the data the pipeline delivers) — "
                "though in smaller organizations one person often wears more than one of "
                "these hats.",
                9,
            ),
            LessonSpec(
                "ETL vs. ELT",
                "ETL (Extract, Transform, Load) transforms data *before* loading it into the "
                "destination — the classic pattern when the destination (often a traditional "
                "data warehouse) has limited compute and storage relative to a dedicated "
                "transformation server, so you shape the data down before it arrives. ELT "
                "(Extract, Load, Transform) instead loads raw data into the destination first "
                "and transforms it there, using the destination's own compute — this became "
                "the dominant pattern as cloud data warehouses (which can scale compute "
                "elastically and cheaply) made in-warehouse transformation practical, and it "
                "has the advantage of keeping a full copy of raw source data available if a "
                "transformation turns out to be wrong and needs to be redone. Neither is "
                "strictly superior — ETL still makes sense when the destination genuinely "
                "can't handle raw volume, or when transformation must happen before data "
                "leaves a compliance boundary.",
                10,
            ),
        ]),
        SectionSpec("Storage Systems", [
            LessonSpec(
                "Data Warehouses vs. Data Lakes",
                "A data warehouse stores structured, schema-defined data optimized for fast "
                "analytical (OLAP) queries — typically using a columnar storage format, which "
                "reads only the specific columns a query needs rather than entire rows, "
                "dramatically speeding up aggregate queries over huge tables. A data lake "
                "stores data in its raw, often semi-structured or unstructured form (JSON "
                "logs, images, raw CSVs) at low cost, with schema applied only when the data "
                "is read (\"schema-on-read\") rather than enforced up front (\"schema-on-"
                "write\", the warehouse approach) — this trades query performance and "
                "consistency guarantees for flexibility and cheaper storage of data whose "
                "eventual use isn't fully known yet. A \"lakehouse\" architecture (e.g. Delta "
                "Lake, Apache Iceberg) is a more recent attempt to combine data-lake storage "
                "economics with data-warehouse-style transactional guarantees and query "
                "performance on top of it.",
                11,
            ),
            LessonSpec(
                "Batch vs. Streaming Processing",
                "Batch processing runs on accumulated data at scheduled intervals (hourly, "
                "nightly) — simpler to reason about and debug, and the right choice when "
                "some latency between an event happening and it showing up in analytics is "
                "acceptable. Streaming processing handles each event as it arrives, "
                "continuously, with tools like Apache Kafka (for durably transporting the "
                "event stream) and Apache Flink or Spark Structured Streaming (for processing "
                "it) — necessary when a business genuinely needs near-real-time results (fraud "
                "detection, live dashboards, alerting). Streaming systems are meaningfully "
                "harder to build correctly: they have to handle out-of-order events, define "
                "what a "
                "\"window\" of time even means when events can arrive late, and reason about "
                "at-least-once versus exactly-once delivery guarantees — complexity a batch "
                "pipeline simply doesn't have to deal with.",
                11,
            ),
        ]),
        SectionSpec("Modeling for Analytics", [
            LessonSpec(
                "Star Schemas: Fact and Dimension Tables",
                "A star schema organizes a data warehouse around a central fact table "
                "(one row per business event — a sale, a page view, a shipment — holding "
                "measurable, typically numeric values like quantity or amount, plus foreign "
                "keys) surrounded by dimension tables (descriptive context about the entities "
                "in the fact table — a `dim_customer` table, a `dim_product` table, a "
                "`dim_date` table). This is a deliberate, useful *denormalization* relative to "
                "the 3NF schemas covered in the SQL course: dimension tables often aren't "
                "further normalized, because the goal here is fast, simple analytical queries "
                "(join the fact table to a few dimension tables) rather than minimizing "
                "storage redundancy or preventing update anomalies, which matter far less for "
                "data that's loaded in bulk and rarely updated in place.",
                12,
            ),
            LessonSpec(
                "Slowly Changing Dimensions",
                "Dimension attributes change over time — a customer moves city, a product "
                "gets reclassified into a different category — and a Slowly Changing "
                "Dimension (SCD) strategy defines how the warehouse handles that. Type 1 "
                "simply overwrites the old value with the new one, losing history but keeping "
                "the table simple — appropriate when the old value genuinely doesn't matter "
                "for historical analysis. Type 2 instead inserts a *new* row for the changed "
                "entity, with effective-date columns (and often a `is_current` flag) marking "
                "which row is valid for which time period, preserving full history at the "
                "cost of a larger dimension table and joins that must account for time. Type "
                "2 is the default choice whenever \"what did this look like as of the date of "
                "this fact\" is a question the business will actually ask.",
                11,
            ),
        ]),
    ],
)


ALL_COURSES: list[CourseSpec] = [
    PYTHON_I,
    PYTHON_II,
    SQL,
    LINEAR_ALGEBRA,
    DSA,
    ALGORITHMS,
    DATA_ENGINEERING,
]


async def seed_default_courses(db: AsyncSession) -> int:
    """Idempotent: only creates a course if no row with its slug exists yet.
    Never touches or overwrites an existing course (including one an admin
    has since edited), so this is safe to call on every app startup.

    Returns the number of courses newly created.
    """
    # Gunicorn boots multiple workers in parallel and each calls this on
    # startup. Without a lock, two workers can both read the same
    # "not yet seeded" snapshot and both try to INSERT the same slug — the
    # loser crashes with a UniqueViolationError, which fails that worker's
    # startup and (since a worker that fails to boot kills the gunicorn
    # master) took down the *whole* app on the deploy that wiped the
    # database. pg_advisory_xact_lock serializes the seeders: the second
    # worker blocks here until the first commits, then its own query below
    # sees the just-committed rows and has nothing left to do.
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SEED_LOCK_KEY})

    existing_slugs = set(
        (await db.execute(select(Course.slug))).scalars().all()
    )
    # Two passes: create all courses first (so every prerequisite_slug can
    # resolve to a real id), then wire up prerequisite_course_id.
    slug_to_id: dict[str, object] = {}
    created = 0

    for spec in ALL_COURSES:
        if spec.slug in existing_slugs:
            existing = (await db.execute(select(Course.id).where(Course.slug == spec.slug))).scalar_one()
            slug_to_id[spec.slug] = existing
            continue

        course = Course(
            title=spec.title,
            slug=spec.slug,
            description=spec.description,
            difficulty=spec.difficulty,
            is_published=True,
            instructor_id=None,  # platform-authored default content
            estimated_hours=spec.estimated_hours,
            skills=spec.skills,
            specialization=spec.specialization,
        )
        db.add(course)
        await db.flush()
        slug_to_id[spec.slug] = course.id

        for s_idx, section_spec in enumerate(spec.sections):
            section = CourseSection(course_id=course.id, title=section_spec.title, order_index=s_idx)
            db.add(section)
            await db.flush()
            for l_idx, lesson_spec in enumerate(section_spec.lessons):
                db.add(Lesson(
                    section_id=section.id,
                    title=lesson_spec.title,
                    content_type=lesson_spec.content_type,
                    content_body=lesson_spec.content_body,
                    order_index=l_idx,
                    duration_minutes=lesson_spec.duration_minutes,
                ))
        created += 1

    if created:
        # Second pass: wire prerequisites now that every course has an id.
        for spec in ALL_COURSES:
            if spec.prerequisite_slug is None:
                continue
            course_id = slug_to_id.get(spec.slug)
            prereq_id = slug_to_id.get(spec.prerequisite_slug)
            if course_id is None or prereq_id is None:
                continue
            course = await db.get(Course, course_id)
            if course is not None and course.prerequisite_course_id is None:
                course.prerequisite_course_id = prereq_id
        await db.commit()

    return created
