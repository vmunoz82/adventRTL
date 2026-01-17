# Programming Challenge: Range and ID Analysis

## Problem Description

You are given a dataset structured into two parts, separated by a blank line.

1.  **Inclusion Ranges:** A list of inclusive integer ranges (e.g., `10-14`).
2.  **Query IDs:** A list of individual integers.

An ID is considered "valid" if it falls within at least one of the specified inclusion ranges.

### Example Data

```
1-4
8-12
14-15
10-16

0
2
8
13
20
```

---

## Part One: Counting Valid Query IDs

### Task

Given the two-part dataset, determine how many of the **Query IDs** are "valid".

### Example Walkthrough

Using the example data:

-   ID `0`: Not in any range (invalid).
-   ID `2`: In range `1-4` (valid).
-   ID `8`: In range `8-12` (valid).
-   ID `13`: In range `10-16` (valid).
-   ID `20`: Not in any range (invalid).

**Result for Example:** `3` of the query IDs are valid.

---

## Part Two: Counting All Unique Valid IDs

### Task

Given only the **Inclusion Ranges**, determine the total number of unique IDs that are considered "valid". The list of **Query IDs** is not used for this part.

This task requires calculating the size of the union of all the given integer ranges, accounting for any overlaps.

### Example Walkthrough

Using the example ranges:

-   `1-4` -> IDs: `1, 2, 3, 4`
-   `8-12` -> IDs: `8, 9, 10, 11, 12`
-   `14-15` -> IDs: `14, 15`
-   `10-16` -> IDs: `10, 11, 12, 13, 14, 15, 16`

The unique IDs covered by the union of these ranges are `1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15, 16`.

**Result for Example:** The total count of unique valid IDs is `13`.
