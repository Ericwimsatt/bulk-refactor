file names have _ between them
Streamline creation of processes (all share some arguments?)
progress tracker is better visually (webserver?)

# Multi-Step Processes
A task is a unit of work that can be represented by calling 1

1 A job consists of several tasks
2 A job can be created by passing a list of tasks to it to complete serially. [can have multiple functions to create a job]
3 job can be started, paused, restarted
    4 due to 2+3, a dead Job can be restored from local storage. (Task list, what's done?, what's todo, what branches its responsible for)
5 job keeps a list of user action items(openCode errors, etc.)
6 job pauses itself when it cannot continue and needs user action
7 As tasks complete, progress is written to a shared progress file
8 Job optionally may have a title describing the operation