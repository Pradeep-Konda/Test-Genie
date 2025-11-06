Feature: Products Resource

  Scenario: List all products (Happy Path)
    When I send a GET request to "/api/products/"
    Then the response status should be 200
    And the response body should contain a list of products with fields "id", "name", and "price"
    And the response time should be less than 1000ms

  Scenario: List products with no products present (Edge Case)
    Given the product database is empty
    When I send a GET request to "/api/products/"
    Then the response status should be 200
    And the response body should be an empty list

  Scenario: List products - SQL injection attempt (Security)
    When I send a GET request to "/api/products/?sort=name;DROP TABLE products;"
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: List products - excessive requests (Performance)
    When I send 200 GET requests to "/api/products/" in 1 minute
    Then 99% of the responses should have a response time less than 1000ms

  Scenario: Add a new product (Happy Path)
    Given the following product data:
      | name   | price  |
      | Tablet | 299.99 |
    When I send a POST request to "/api/products/" with the product data
    Then the response status should be 201
    And the response body should contain:
      | id | name   | price  |
      | 3  | Tablet | 299.99 |
    And the response time should be less than 1000ms

  Scenario: Add product with missing price (Negative/Error)
    Given the following product data:
      | name   |
      | Tablet |
    When I send a POST request to "/api/products/" with the product data
    Then the response status should be 400

  Scenario: Add product with negative price (Edge Case)
    Given the following product data:
      | name   | price  |
      | Tablet | -10.00 |
    When I send a POST request to "/api/products/" with the product data
    Then the response status should be 400

  Scenario: Add product with empty name (Edge Case)
    Given the following product data:
      | name | price  |
      |      | 299.99 |
    When I send a POST request to "/api/products/" with the product data
    Then the response status should be 400

  Scenario: Add product - XSS attack in name (Security)
    Given the following product data:
      | name           | price  |
      | <script>bad()</script> | 299.99 |
    When I send a POST request to "/api/products/" with the product data
    Then the response status should not be 500
    And the response body should not reflect the script tag

  Scenario: Add product - unauthorized access (Security)
    Given I am not authenticated
    When I send a POST request to "/api/products/" with valid product data
    Then the response status should be 401

  Scenario: Get product by ID (Happy Path)
    Given a product exists with id 1
    When I send a GET request to "/api/products/1"
    Then the response status should be 200
    And the response body should contain:
      | id | name   | price   |
      | 1  | Laptop | 999.99  |
    And the response time should be less than 1000ms

  Scenario: Get product by non-existent ID (Negative/Error)
    When I send a GET request to "/api/products/9999"
    Then the response status should be 404
    And the response body should contain "error"

  Scenario: Get product by ID with invalid ID type (Negative/Error)
    When I send a GET request to "/api/products/abc"
    Then the response status should be 400

  Scenario: Get product by ID - ID at lower boundary (Edge Case)
    When I send a GET request to "/api/products/0"
    Then the response status should be 404

  Scenario: Get product by ID - SQL injection attempt (Security)
    When I send a GET request to "/api/products/1;DROP TABLE products;"
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: Get product by ID - unauthorized access (Security)
    Given I am not authenticated
    When I send a GET request to "/api/products/1"
    Then the response status should be 401