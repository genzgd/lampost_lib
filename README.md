## Lampost Library

A framework library initially developed to support the Lampost Mud.  Current components include:

### lampost.db

A JSON based fast and efficient storage mechanism for Python objects and their relationships.  Persisted fields are
identified by descriptor classes.  Full inheritance (including "mixins") is supported.  Default values (including
empty collections) are not persisted to improve storage usage and network efficiency.
