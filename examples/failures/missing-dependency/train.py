print('Failure scenario: missing workspace dependency', flush=True)
import package_that_does_not_exist  # noqa: F401
