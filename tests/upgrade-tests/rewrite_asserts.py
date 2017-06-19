import pytest

# This file needs to be imported before any of the modules specified below.
# Otherwise, we won't get good assert output from pytest

pytest.register_assert_rewrite('utils')
pytest.register_assert_rewrite('validation')
