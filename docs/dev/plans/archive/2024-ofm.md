# Object-File Mapping

FloPy aims to provide an object-oriented interface to MODFLOW 6. This involves translating between user-facing Python objects and MODFLOW 6 input files. This task is analogous to that performed by an object-relational mapping (ORM) library for a relational database.

ORM software, [Django](https://www.djangoproject.com/) for instance, aims to hide the details of database access from the user:

> When some (user) code creates a subclass of `models.Model`, a lot goes on behind the scenes in order to present a reasonably normal looking Python class to the user, whilst providing the necessary database support when it comes time to save or load instances of the model.[^1]



[^1]: https://code.djangoproject.com/wiki/DevModelCreation.
