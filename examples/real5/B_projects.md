# Team project tracker

## Requirements

1. Members can create projects and invite other members to them.
2. Each project has many tasks; a task belongs to exactly one project.
3. A task may depend on other tasks in the same project; a task cannot depend on itself and dependency cycles are not allowed.
4. Members can assign a task to one member and set its due date, estimate in hours and priority.
5. A member has a display name, an email address, a time zone and a weekly capacity in hours.
6. Members can mark a task done; a task cannot be marked done while a task it depends on is still open.
7. Members can archive a project; an archived project is read-only and its tasks cannot be edited.
8. Each member sees the tasks assigned to them, ordered by due date.

## Constraints

- Team of 2, TypeScript, PostgreSQL available.
