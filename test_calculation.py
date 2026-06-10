import pytest
from calculation import add, subtract


class TestAdd:
    """Tests for add(a, b) — returns the sum of two numbers."""

    def test_add_two_positive(self):
        assert add(1, 2) == 3

    def test_add_two_negative(self):
        assert add(-1, -2) == -3

    def test_add_positive_and_negative(self):
        assert add(5, -3) == 2

    def test_add_with_zero(self):
        assert add(0, 7) == 7
        assert add(7, 0) == 7
        assert add(0, 0) == 0

    def test_add_floating_point(self):
        assert add(1.5, 2.5) == 4.0

    def test_add_large_numbers(self):
        assert add(10**9, 10**9) == 2 * 10**9

    def test_add_type_error_on_none(self):
        with pytest.raises(TypeError):
            add(None, 1)

    def test_add_type_error_on_string(self):
        with pytest.raises(TypeError):
            add("a", 1)


class TestSubtract:
    """Tests for subtract(a, b) — returns the difference a - b."""

    def test_subtract_smaller_from_larger(self):
        assert subtract(5, 3) == 2

    def test_subtract_larger_from_smaller(self):
        assert subtract(3, 5) == -2

    def test_subtract_two_negative(self):
        assert subtract(-5, -3) == -2

    def test_subtract_negative_from_positive(self):
        assert subtract(5, -3) == 8

    def test_subtract_with_zero(self):
        assert subtract(7, 0) == 7
        assert subtract(0, 7) == -7
        assert subtract(0, 0) == 0

    def test_subtract_floating_point(self):
        assert subtract(5.5, 2.2) == pytest.approx(3.3)

    def test_subtract_large_numbers(self):
        assert subtract(10**9, 1) == 10**9 - 1

    def test_subtract_type_error_on_none(self):
        with pytest.raises(TypeError):
            subtract(None, 1)

    def test_subtract_type_error_on_string(self):
        with pytest.raises(TypeError):
            subtract("a", 1)
