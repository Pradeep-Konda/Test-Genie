Feature: Order Management

  Scenario: List all orders (Happy Path)
    When I send a GET request to /api/orders/
    Then the response status should be 200
    And the response body should be a list of orders with fields id, user_id, product_id, and quantity
    And the response time should be less than 1000ms

  Scenario: List orders with no orders present (Edge Case)
    Given the order database is empty
    When I send a GET request to /api/orders/
    Then the response status should be 200
    And the response body should be an empty list

  Scenario: List orders - SQL injection attempt (Security)
    When I send a GET request to /api/orders/?user_id=' OR '1'='1
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: List orders - excessive requests (Performance)
    When I send 200 GET requests to /api/orders/ in rapid succession
    Then 95% of the responses should have a response time less than 1000ms

  Scenario: Create a new order (Happy Path)
    Given the following order data:
      | user_id | product_id | quantity |
      | 1       | 2          | 3        |
    When I send a POST request to /api/orders/ with the order data
    Then the response status should be 201
    And the response body should contain "id": 3, "user_id": 1, "product_id": 2, "quantity": 3
    And the response time should be less than 1000ms

  Scenario: Create order with missing quantity (Negative/Error)
    Given the following order data:
      | user_id | product_id |
      | 1       | 2          |
    When I send a POST request to /api/orders/ with the order data
    Then the response status should be 400
    And the response body should contain an error message about missing quantity

  Scenario: Create order with zero quantity (Edge Case)
    Given the following order data:
      | user_id | product_id | quantity |
      | 1       | 2          | 0        |
    When I send a POST request to /api/orders/ with the order data
    Then the response status should be 400
    And the response body should contain an error message about invalid quantity

  Scenario: Create order with negative quantity (Edge Case)
    Given the following order data:
      | user_id | product_id | quantity |
      | 1       | 2          | -5       |
    When I send a POST request to /api/orders/ with the order data
    Then the response status should be 400
    And the response body should contain an error message about invalid quantity

  Scenario: Create order with non-existent user_id (Negative/Error)
    Given the following order data:
      | user_id | product_id | quantity |
      | 9999    | 2          | 1        |
    When I send a POST request to /api/orders/ with the order data
    Then the response status should be 400
    And the response body should contain an error message about invalid user_id

  Scenario: Create order - injection attack in user_id (Security)
    Given the following order data:
      | user_id | product_id | quantity |
      | ' OR 1=1-- | 2        | 1        |
    When I send a POST request to /api/orders/ with the order data
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: Create order - excessive requests (Performance)
    When I send 100 POST requests to /api/orders/ with valid order data in rapid succession
    Then 95% of the responses should have a response time less than 1000ms

  Scenario: Get order by ID (Happy Path)
    Given an order with id 1 exists
    When I send a GET request to /api/orders/1
    Then the response status should be 200
    And the response body should contain "id": 1, "user_id": 1, "product_id": 2, "quantity": 1
    And the response time should be less than 1000ms

  Scenario: Get order by non-existent ID (Negative/Error)
    When I send a GET request to /api/orders/9999
    Then the response status should be 404
    And the response body should contain "error": "Order not found"

  Scenario: Get order by ID with invalid ID type (Negative/Error)
    When I send a GET request to /api/orders/abc
    Then the response status should be 400

  Scenario: Get order by ID - path traversal attack (Security)
    When I send a GET request to /api/orders/../../etc/passwd
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: Get order by ID - excessive requests (Performance)
    When I send 100 GET requests to /api/orders/1 in rapid succession
    Then 95% of the responses should have a response time less than 1000ms