Feature:Retrieve users endpoint

  Scenario: Retrieve all users
    When I send a GET request to "/users"
    Then the response status code should be 200
    And the response JSON should be:
      | id | name  |
      | 1  | Alice |
      | 2  | Bob   |