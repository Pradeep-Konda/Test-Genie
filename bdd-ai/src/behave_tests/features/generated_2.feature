Feature:List All Users
  Scenario: Retrieving the list of all users
    When I send a GET request to "/users"
    Then the response status should be 200
    And the response should be a list of users with "id" and "name"