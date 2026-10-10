from rest_framework.views import exception_handler

def custom_exception_handler(exceptions, context):
    response = exception_handler(exceptions, context)
    if response is not None:
        response.data = {
            "error" : {
                "status_code" : response.status_code,
                "detail" : response.data,
            }
        }
    return response