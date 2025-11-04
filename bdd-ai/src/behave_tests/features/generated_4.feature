Feature:Retrieve User by ID
  Scenario: Getting details of a user by a specific ID
    Given a user with id 123 exists
    When I send a GET request to "/users/123"
    Then the response status should be 200
    And the response should contain "id" equal to 123
    And the response should contain "name" equal to "Sample User"