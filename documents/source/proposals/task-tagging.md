---
status: "Accepted"
---
# Task Tagging

We'd like to query for specific tasks in various cases. 

There is no way for user to group/name sets of tasks for such queries.

For example, one may want to tag tasks involved with testing with a label "test" (e.g. to mark tasks relating to testing, or tasks that should be run as part of testing).

Tools may inspect the Task graph and return tasks with the specified labels.

Integration with development environments or editors necessitates tagging tasks relevant for those tools (e.g. tasks one would like to have available to select in a menu).

## Syntax

Tags are specified using sets of strings:

```python

task(
    name="example",
    # ...
    # NOTE: using the python set syntax, not really necessary.
    tags={"testing", "label1"}
)
```

## TODO: internal tags

We may want to reserve some internal tags for specific operations. 
This may require a syntax to delimit user/string tags from system/internal tags (for example, `internal("label")`, or a prefix/separator `makex/label`)
Some internal tags may be used to improve command line or gui tools by creating subsets of tasks.
