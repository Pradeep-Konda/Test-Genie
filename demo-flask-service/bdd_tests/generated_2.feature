Feature: Users Resource

  Scenario: List all users (Happy Path)
    When I send a GET request to "/api/users/"
    Then the response status should be 200
    And the response body should contain a list of users with fields "id", "name", and "email"
    And the response time should be less than 1000ms

  Scenario: List users with no users present (Edge Case)
    Given the user database is empty
    When I send a GET request to "/api/users/"
    Then the response status should be 200
    And the response body should be an empty list

  Scenario: List users - SQL injection attempt (Security)
    When I send a GET request to "/api/users/?sort=name;DROP TABLE users;"
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: List users - excessive requests (Performance)
    When I send 200 GET requests to "/api/users/" in 1 minute
    Then 99% of the responses should have a response time less than 1000ms

  Scenario: Create a new user (Happy Path)
    Given the following user data:
      | name    | email                |
      | Charlie | charlie@example.com  |
    When I send a POST request to "/api/users/" with the user data
    Then the response status should be 201
    And the response body should contain:
      | id | name    | email                |
      | 3  | Charlie | charlie@example.com  |
    And the response time should be less than 1000ms

  Scenario: Create user with missing email (Negative/Error)
    Given the following user data:
      | name    |
      | Charlie |
    When I send a POST request to "/api/users/" with the user data
    Then the response status should be 400

  Scenario: Create user with invalid email format (Negative/Error)
    Given the following user data:
      | name    | email      |
      | Charlie | not-an-email |
    When I send a POST request to "/api/users/" with the user data
    Then the response status should be 400

  Scenario: Create user with empty name (Edge Case)
    Given the following user data:
      | name | email                |
      |      | charlie@example.com  |
    When I send a POST request to "/api/users/" with the user data
    Then the response status should be 400

  Scenario: Create user with duplicate email (Edge Case)
    Given a user exists with email "alice@example.com"
    And the following user data:
      | name  | email              |
      | Alice | alice@example.com  |
    When I send a POST request to "/api/users/" with the user data
    Then the response status should be 409

  Scenario: Create user - XSS attack in name (Security)
    Given the following user data:
      | name           | email                |
      | <script>bad()</script> | xss@example.com |
    When I send a POST request to "/api/users/" with the user data
    Then the response status should not be 500
    And the response body should not reflect the script tag

  Scenario: Create user - unauthorized access (Security)
    Given I am not authenticated
    When I send a POST request to "/api/users/" with valid user data
    Then the response status should be 401

  Scenario: Get user by ID (Happy Path)
    Given a user exists with id 1
    When I send a GET request to "/api/users/1"
    Then the response status should be 200
    And the response body should contain:
      | id | name  | email              |
      | 1  | Alice | alice@example.com  |
    And the response time should be less than 1000ms

  Scenario: Get user by non-existent ID (Negative/Error)
    When I send a GET request to "/api/users/9999"
    Then the response status should be 404
    And the response body should contain "error"

  Scenario: Get user by ID with invalid ID type (Negative/Error)
    When I send a GET request to "/api/users/abc"
    Then the response status should be 400

  Scenario: Get user by ID - ID at lower boundary (Edge Case)
    When I send a GET request to "/api/users/0"
    Then the response status should be 404

  Scenario: Get user by ID - SQL injection attempt (Security)
    When I send a GET request to "/api/users/1;DROP TABLE users;"
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: Get user by ID - unauthorized access (Security)
    Given I am not authenticated
    When I send a GET request to "/api/users/1"
    Then the response status should be 401