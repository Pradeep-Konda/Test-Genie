Feature:Demo Flask Service API

  Scenario: Check service health
    When I send a GET request to "/api/health"
    Then the response status code should be 200
    And the response should contain JSON with "status" equal to "ok"

  Scenario: List all users
    When I send a GET request to "/api/users/"
    Then the response status code should be 200
    And the response should be a JSON array of users

  Scenario: Create a new user
    Given I have a JSON request body with "name" as "Charlie" and "email" as "charlie@example.com"
    When I send a POST request to "/api/users/" with the request body
    Then the response status code should be 201
    And the response should contain JSON with "id", "name" as "Charlie", and "email" as "charlie@example.com"

  Scenario: Get user by ID
    When I send a GET request to "/api/users/1"
    Then the response status code should be 200
    And the response should contain JSON with "id" as 1, "name" as "Alice", and "email" as "alice@example.com"

  Scenario: Get user by ID - user not found
    When I send a GET request to "/api/users/999"
    Then the response status code should be 404
    And the response should contain JSON with "error" as "User not found"

  Scenario: List all products
    When I send a GET request to "/api/products/"
    Then the response status code should be 200
    And the response should be a JSON array of products

  Scenario: Add a new product
    Given I have a JSON request body with "name" as "Tablet" and "price" as 299.99
    When I send a POST request to "/api/products/" with the request body
    Then the response status code should be 201
    And the response should contain JSON with "id", "name" as "Tablet", and "price" as 299.99

  Scenario: Get product by ID
    When I send a GET request to "/api/products/1"
    Then the response status code should be 200
    And the response should contain JSON with "id" as 1, "name" as "Laptop", and "price" as 999.99

  Scenario: Get product by ID - product not found
    When I send a GET request to "/api/products/999"
    Then the response status code should be 404
    And the response should contain JSON with "error" as "Product not found"

  Scenario: List all orders
    When I send a GET request to "/api/orders/"
    Then the response status code should be 200
    And the response should be a JSON array of orders

  Scenario: Create a new order
    Given I have a JSON request body with "user_id" as 1, "product_id" as 2, and "quantity" as 3
    When I send a POST request to "/api/orders/" with the request body
    Then the response status code should be 201
    And the response should contain JSON with "id", "user_id" as 1, "product_id" as 2, and "quantity" as 3

  Scenario: Get order details by ID
    When I send a GET request to "/api/orders/1"
    Then the response status code should be 200
    And the response should contain JSON with "id" as 1, "user_id" as 1, "product_id" as 2, and "quantity" as 1

  Scenario: Get order details by ID - order not found
    When I send a GET request to "/api/orders/999"
    Then the response status code should be 404
    And the response should contain JSON with "error" as "Order not found"