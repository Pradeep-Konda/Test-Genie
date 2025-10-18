Certainly! Here are the Gherkin BDD scenarios for the given use cases of the `add` function:

```gherkin
Feature: Add two values

  Scenario: Add two positive integers
    Given the first value is 1
    And the second value is 2
    When I add the two values
    Then the result should be 3

  Scenario: Add two negative integers
    Given the first value is -1
    And the second value is -2
    When I add the two values
    Then the result should be -3

  Scenario: Add two zeros
    Given the first value is 0
    And the second value is 0
    When I add the two values
    Then the result should be 0

  Scenario: Add two floating point numbers
    Given the first value is 1.5
    And the second value is 2.5
    When I add the two values
    Then the result should be 4.0

  Scenario: Concatenate two strings
    Given the first value is "foo"
    And the second value is "bar"
    When I add the two values
    Then the result should be "foobar"

  Scenario: Concatenate two lists
    Given the first value is [1,2]
    And the second value is [3,4]
    When I add the two values
    Then the result should be [1,2,3,4]

  Scenario: Add None and an integer
    Given the first value is None
    And the second value is 1
    When I add the two values
    Then a TypeError should be raised
```

Let me know if you'd like scenario outlines or table formatting!