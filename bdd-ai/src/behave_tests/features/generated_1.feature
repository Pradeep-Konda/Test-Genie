Feature:TestResult Class Functionality

  Scenario: Create an instance of TestResult with valid string values
    Given I have the strings "Analysis details", "Feature scenario steps", and "Test output"
    When I create a TestResult with these values
    Then the analysis field is "Analysis details"
    And the featureText field is "Feature scenario steps"
    And the executionOutput field is "Test output"

  Scenario: Create an instance with null values
    Given I have null values for analysis, featureText, and executionOutput
    When I create a TestResult with these values
    Then the analysis field is null
    And the featureText field is null
    And the executionOutput field is null
    And no exception is thrown

  Scenario: Retrieve analysis value after initialization
    Given a TestResult initialized with analysis "Some analysis"
    When I call getAnalysis()
    Then the result is "Some analysis"

  Scenario: Set analysis to a new valid string value
    Given a TestResult with analysis "Old analysis"
    When I set analysis to "Updated analysis"
    Then getAnalysis() returns "Updated analysis"

  Scenario: Set analysis to null
    Given a TestResult with analysis "Previous analysis"
    When I set analysis to null
    Then getAnalysis() returns null

  Scenario: Retrieve featureText value after initialization
    Given a TestResult initialized with featureText "Initial steps"
    When I call getFeatureText()
    Then the result is "Initial steps"

  Scenario: Set featureText to a valid string
    Given a TestResult with featureText "Previous steps"
    When I set featureText to "Given, When, Then"
    Then getFeatureText() returns "Given, When, Then"

  Scenario: Set featureText to null
    Given a TestResult with featureText "Some steps"
    When I set featureText to null
    Then getFeatureText() returns null

  Scenario: Retrieve executionOutput after initialization
    Given a TestResult initialized with executionOutput "Execution result"
    When I call getExecutionOutput()
    Then the result is "Execution result"

  Scenario: Set executionOutput to a valid string
    Given a TestResult with executionOutput "Failed"
    When I set executionOutput to "Passed"
    Then getExecutionOutput() returns "Passed"

  Scenario: Set executionOutput to null
    Given a TestResult with executionOutput "To be cleared"
    When I set executionOutput to null
    Then getExecutionOutput() returns null

  Scenario: Invoke toString after object initialization
    Given a TestResult with analysis "A", featureText "B", executionOutput "C"
    When I call toString()
    Then the result is "TestResult{analysis='A', featureText='B', executionOutput='C'}"

  Scenario: Invoke toString when fields are null
    Given a TestResult with analysis null, featureText null, executionOutput null
    When I call toString()
    Then the result is "TestResult{analysis='null', featureText='null', executionOutput='null'}"