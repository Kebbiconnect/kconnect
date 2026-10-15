"""All JSON request contracts in this API use an object, never a bare array/scalar."""
from rest_framework.parsers import JSONParser
from rest_framework.exceptions import ParseError

class JSONObjectParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type=media_type, parser_context=parser_context)
        if not isinstance(data, dict):
            raise ParseError('Send a JSON object with named fields, not an array or scalar.')
        return data
