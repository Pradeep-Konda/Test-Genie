Feature:Get user details by ID

  Scenario: Get user details by ID
    Given a user exists with id 42
    When I send a GET request to "/users/42"
    Then the response status code should be 200
    And the response JSON should be:
      | id | name        |
      | 42 | Sample User |