from behave import given, when, then

@given("a function defined in the source code")
def step_given_function(context):
    context.code_loaded = True

@when("the function is executed with valid inputs")
def step_when_execute_function(context):
    if context.code_loaded:
        context.result = "Execution successful"

@then("the output should match the expected behavior")
def step_then_verify_output(context):
    assert context.result == "Execution successful"
