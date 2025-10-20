Certainly! Here are the Gherkin BDD scenarios for your provided use cases:

---

**Feature: Health check of the service**

```gherkin
Scenario: Health check success
  When I send a GET request to "/health"
  Then the response status code should be 200
  And the response should contain JSON:
    """
    {
      "status": "ok"
    }
    """
```

---

**Feature: User listing**

```gherkin
Scenario: List all users
  When I send a GET request to "/users"
  Then the response status code should be 200
  And the response should contain JSON:
    """
    [
      {"id": 1, "name": "Alice"},
      {"id": 2, "name": "Bob"}
    ]
    """
```

---

**Feature: Retrieve user by ID**

```gherkin
Scenario: Get existing user by ID
  Given a user with id 123 exists and is named "Sample User"
  When I send a GET request to "/users/123"
  Then the response status code should be 200
  And the response should contain JSON:
    """
    {
      "id": 123,
      "name": "Sample User"
    }
    """
```

---

**Feature: Create a new user**

```gherkin
Scenario: Create new user
  Given I have the following user data:
    | name  |
    | Carol |
  When I send a POST request to "/users" with JSON body:
    """
    {"name": "Carol"}
    """
  Then the response status code should be 201
  And the response should contain JSON:
    """
    {
      "message": "User created",
      "user": {"name": "Carol"}
    }
    """
```

---

Let me know if you need further breakdowns, more scenarios (like error cases), or want these in a different format!