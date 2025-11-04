Feature: API Endpoint Testing

  Scenario: Test GET /__init__
    Given the API endpoint '/__init__'
    When I send a GET request
    Then I should receive a 200 OK response

