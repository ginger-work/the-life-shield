"""
The Life Shield — Unit Tests: Input Validators
Tests for email normalization, password policy, phone validation, and name validation.
"""

import pytest

from app.core.validators import (
    ValidationError,
    is_password_valid,
    normalize_email,
    normalize_phone,
    validate_email,
    validate_name,
    validate_password_strength,
    validate_phone,
    MIN_PASSWORD_LENGTH,
)


# ═════════════════════════════════════════════════════════════════════════════
# EMAIL VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeEmail:
    def test_strips_whitespace(self):
        assert normalize_email("  user@example.com  ") == "user@example.com"

    def test_lowercases(self):
        assert normalize_email("User@Example.COM") == "user@example.com"

    def test_valid_email_passes(self):
        assert normalize_email("valid@domain.com") == "valid@domain.com"

    def test_subdomain_email(self):
        assert normalize_email("user@mail.subdomain.org") == "user@mail.subdomain.org"

    def test_plus_addressing(self):
        assert normalize_email("user+tag@example.com") == "user+tag@example.com"

    def test_raises_on_empty(self):
        with pytest.raises(ValidationError) as exc:
            normalize_email("")
        assert exc.value.field == "email"

    def test_raises_on_missing_at(self):
        with pytest.raises(ValidationError):
            normalize_email("notanemail.com")

    def test_raises_on_missing_domain(self):
        with pytest.raises(ValidationError):
            normalize_email("user@")

    def test_raises_on_missing_tld(self):
        with pytest.raises(ValidationError):
            normalize_email("user@domain")

    def test_raises_on_none(self):
        with pytest.raises((ValidationError, AttributeError)):
            normalize_email(None)  # type: ignore[arg-type]

    def test_spaces_in_middle_invalid(self):
        with pytest.raises(ValidationError):
            normalize_email("user name@example.com")


class TestValidateEmail:
    def test_valid_email_returns_true(self):
        assert validate_email("user@example.com") is True

    def test_invalid_email_returns_false(self):
        assert validate_email("notanemail") is False

    def test_empty_returns_false(self):
        assert validate_email("") is False


# ═════════════════════════════════════════════════════════════════════════════
# PASSWORD VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

class TestValidatePasswordStrength:
    def test_strong_password_has_no_violations(self, valid_password):
        violations = validate_password_strength(valid_password)
        assert violations == []

    def test_empty_password_fails(self):
        violations = validate_password_strength("")
        assert len(violations) > 0

    def test_too_short_fails(self):
        violations = validate_password_strength("Short1!")
        assert any("characters" in v for v in violations)

    def test_minimum_length_boundary(self):
        """Exactly MIN_PASSWORD_LENGTH chars with all requirements."""
        pw = "Secure1!" + "a" * (MIN_PASSWORD_LENGTH - 8)
        violations = validate_password_strength(pw)
        assert violations == []

    def test_no_uppercase_fails(self):
        violations = validate_password_strength("alllowercase1!")
        assert any("uppercase" in v.lower() for v in violations)

    def test_no_lowercase_fails(self):
        violations = validate_password_strength("ALLUPPERCASE1!")
        assert any("lowercase" in v.lower() for v in violations)

    def test_no_digit_fails(self):
        violations = validate_password_strength("NoDigitsHere!!")
        assert any("digit" in v.lower() for v in violations)

    def test_no_special_char_fails(self):
        violations = validate_password_strength("NoSpecialChars12")
        assert any("special" in v.lower() for v in violations)

    def test_multiple_violations_reported(self):
        violations = validate_password_strength("short")
        assert len(violations) >= 2  # too short + missing chars

    def test_various_special_chars_accepted(self, valid_password):
        special_chars = "!@#$%^&*()_+-=[]{}|;:'\",.<>?`~"
        for char in special_chars:
            pw = f"SecurePass1{char}"
            violations = validate_password_strength(pw)
            assert violations == [], f"Should accept special char: {char!r}"

    def test_none_password_fails(self):
        violations = validate_password_strength(None)  # type: ignore[arg-type]
        assert len(violations) > 0

    def test_unicode_chars_in_password(self):
        """Unicode characters in passwords are accepted (length is by char count)."""
        pw = "Pässwörd!1abc"
        violations = validate_password_strength(pw)
        # should pass all checks (has upper, lower, digit, special, length)
        assert violations == []


class TestIsPasswordValid:
    def test_strong_password_is_valid(self, valid_password):
        assert is_password_valid(valid_password) is True

    def test_weak_passwords_invalid(self, weak_passwords):
        for pw in weak_passwords:
            assert is_password_valid(pw) is False, f"Expected {pw!r} to be invalid"


# ═════════════════════════════════════════════════════════════════════════════
# PHONE VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

class TestValidatePhone:
    def test_valid_10_digit(self):
        assert validate_phone("9193334444") is True

    def test_valid_with_country_code(self):
        assert validate_phone("+19193334444") is True

    def test_valid_formatted(self):
        assert validate_phone("(919) 333-4444") is True

    def test_valid_dashes(self):
        assert validate_phone("919-333-4444") is True

    def test_valid_dots(self):
        assert validate_phone("919.333.4444") is True

    def test_empty_returns_false(self):
        assert validate_phone("") is False

    def test_too_few_digits(self):
        assert validate_phone("91933344") is False

    def test_letters_in_number(self):
        assert validate_phone("555-CALL-NOW") is False


class TestNormalizePhone:
    def test_10_digit_to_e164(self):
        assert normalize_phone("9193334444") == "+19193334444"

    def test_formatted_to_e164(self):
        assert normalize_phone("(919) 333-4444") == "+19193334444"

    def test_with_country_code_to_e164(self):
        assert normalize_phone("+19193334444") == "+19193334444"

    def test_with_1_prefix_to_e164(self):
        assert normalize_phone("19193334444") == "+19193334444"

    def test_raises_on_empty(self):
        with pytest.raises(ValidationError) as exc:
            normalize_phone("")
        assert exc.value.field == "phone"

    def test_raises_on_invalid(self):
        with pytest.raises(ValidationError):
            normalize_phone("555-CALL")


# ═════════════════════════════════════════════════════════════════════════════
# NAME VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateName:
    def test_valid_name_returned(self):
        assert validate_name("  Deon  ", field="first_name") == "Deon"

    def test_strips_whitespace(self):
        assert validate_name("  Robinson  ", field="last_name") == "Robinson"

    def test_raises_on_empty(self):
        with pytest.raises(ValidationError) as exc:
            validate_name("", field="first_name")
        assert exc.value.field == "first_name"

    def test_raises_on_whitespace_only(self):
        with pytest.raises(ValidationError):
            validate_name("   ", field="first_name")

    def test_raises_on_too_long(self):
        with pytest.raises(ValidationError):
            validate_name("A" * 101, field="first_name")

    def test_exactly_100_chars_accepted(self):
        name = "A" * 100
        result = validate_name(name)
        assert result == name

    def test_hyphenated_name_accepted(self):
        assert validate_name("Smith-Jones") == "Smith-Jones"

    def test_apostrophe_in_name_accepted(self):
        assert validate_name("O'Brien") == "O'Brien"
