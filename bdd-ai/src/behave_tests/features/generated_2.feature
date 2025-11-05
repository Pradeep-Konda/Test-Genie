Feature: User Management

  Scenario: List all users (Happy Path)
    When I send a GET request to /api/users/
    Then the response status should be 200
    And the response body should be a list of users with fields id, name, and email
    And the response time should be less than 1000ms

  Scenario: List users with no users present (Edge Case)
    Given the user database is empty
    When I send a GET request to /api/users/
    Then the response status should be 200
    And the response body should be an empty list

  Scenario: List users - SQL injection attempt (Security)
    When I send a GET request to /api/users/?name=' OR '1'='1
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: List users - excessive requests (Performance)
    When I send 200 GET requests to /api/users/ in rapid succession
    Then 95% of the responses should have a response time less than 1000ms

  Scenario: Create a new user (Happy Path)
    Given the following user data:
      | name    | email               |
      | Charlie | charlie@example.com |
    When I send a POST request to /api/users/ with the user data
    Then the response status should be 201
    And the response body should contain "id": 3, "name": "Charlie", "email": "charlie@example.com"
    And the response time should be less than 1000ms

  Scenario: Create user with missing email (Negative/Error)
    Given the following user data:
      | name    |
      | Charlie |
    When I send a POST request to /api/users/ with the user data
    Then the response status should be 400
    And the response body should contain an error message about missing email

  Scenario: Create user with invalid email format (Negative/Error)
    Given the following user data:
      | name    | email      |
      | Charlie | not-an-email |
    When I send a POST request to /api/users/ with the user data
    Then the response status should be 400
    And the response body should contain an error message about invalid email

  Scenario: Create user with null name (Edge Case)
    Given the following user data:
      | name | email               |
      | null | charlie@example.com |
    When I send a POST request to /api/users/ with the user data
    Then the response status should be 400
    And the response body should contain an error message about missing name

  Scenario: Create user - XSS attack in name (Security)
    Given the following user data:
      | name           | email               |
      | <script>bad()</script> | charlie@example.com |
    When I send a POST request to /api/users/ with the user data
    Then the response status should not be 500
    And the response body should not reflect the script tag

  Scenario: Create user - excessive requests (Performance)
    When I send 100 POST requests to /api/users/ with valid user data in rapid succession
    Then 95% of the responses should have a response time less than 1000ms

  Scenario: Get user by ID (Happy Path)
    Given a user with id 1 exists
    When I send a GET request to /api/users/1
    Then the response status should be 200
    And the response body should contain "id": 1, "name": "Alice", "email": "alice@example.com"
    And the response time should be less than 1000ms

  Scenario: Get user by non-existent ID (Negative/Error)
    When I send a GET request to /api/users/9999
    Then the response status should be 404
    And the response body should contain "error": "User not found"

  Scenario: Get user by ID with invalid ID type (Negative/Error)
    When I send a GET request to /api/users/abc
    Then the response status should be 400

  Scenario: Get user by ID - path traversal attack (Security)
    When I send a GET request to /api/users/../../etc/passwd
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: Get user by ID - excessive requests (Performance)
    When I send 100 GET requests to /api/users/1 in rapid succession
    Then 95% of the responses should have a response time less than 1000ms