from mesh.constants import *
from mesh.exceptions import *
from mesh.request import *
from mesh.resource import *
from mesh.util import pluralize
from scheme import *

"""
The requests generated by this module introduce a variety of new field aspects:

deferred (boolean)
    If True, values for the field will only be returned in a get or query request
    when explicitly requested through the use of include.
oncreate/onput/onupdate (boolean)
    If True, a value for this field can or must be specified in a request of the
    named type (create, put or update). If False, a value for this field cannot
    be specified in a request of the named type. If None, no effect.
operators (list of strings)
    If specified, indicates the operators which this field supports for query requests.
readonly (boolean)
    If True, a value for the field cannot be specified in create/update/put requests,
    but is returned in get/query requests.
returned (list of strings)
    If specified, indicates the requests (typically one or more of create, update,
    delete and put) which should return a value for this field in a successful
    response.
sortable (boolean)
    If True, this field can be specified as a sort parameter in query requests.
"""

class OperatorConstructor(object):
    operators = {
        'equal': 'Equals',
        'iequal': 'Case-insensitive equals.',
        'not': 'Not equal.',
        'inot': 'Case-insensitive not equal.',
        'prefix': 'Prefix search.',
        'iprefix': 'Case-insensitive prefix search.',
        'suffix': 'Suffix search.',
        'isuffix': 'Case-insensitive suffix search.',
        'contains': 'Contains.',
        'icontains': 'Case-insensitive contains.',
        'gt': 'Greater then.',
        'gte': 'Greater then or equal to.',
        'lt': 'Less then.',
        'lte': 'Less then or equal to.',
        'null': 'Is null.',
        'in': 'In given values.',
        'notin': 'Not in given values.',
    }

    @classmethod
    def construct(cls, operators, field):
        supported = field.operators
        if isinstance(supported, basestring):
            supported = supported.split(' ')

        for operator in supported:
            if isinstance(operator, Field):
                operators[operator.name] = operator
                continue

            description = cls.operators.get(operator)
            if description:
                constructor = getattr(cls, '_construct_%s_operator' % operator, None)
                if constructor:
                    operator_field = constructor(field, description)
                else:
                    name = '%s__%s' % (field.name, operator)
                    operator_field = clone_field(field, name, description)
                operators[operator_field.name] = operator_field

        return operators

    @classmethod
    def _construct_equal_operator(cls, field, description):
        return clone_field(field, field.name, description)

    @classmethod
    def _construct_in_operator(cls, field, description):
        return Sequence(clone_field(field), name='%s__in' % field.name,
            description=description, nonnull=True)

    @classmethod
    def _construct_notin_operator(cls, field, description):
        return Sequence(clone_field(field), name='%s__notin' % field.name,
            description=description, nonnull=True)

    @classmethod
    def _construct_null_operator(cls, field, description):
        return Boolean(name='%s__null' % field.name, description=description, nonnull=True)

def add_query_operator(resource, operator):
    if 'query' in resource.requests:
        resource.requests['query'].schema.structure['query'].insert(operator)
    else:
        raise TypeError()

def add_schema_field(resource, field):
    """Adds ``field`` to the schema of ``resource``, updating all requests
    to include ``field``, where appropriate.

    :param resource: The :class:`mesh.resource.Resource` to modify.

    """


    resource.schema[field.name] = field
    if 'get' in resource.requests:
        request = resource.requests['get']
        request.responses[OK].schema.insert(field)

        request.schema.insert(construct_fields_field({field.name: field},
            request.schema.get('fields')), overwrite=True)

        if field.deferred:
            request.schema.insert(construct_include_field({field.name: field},
                request.schema.get('include')), overwrite=True)
        else:
            request.schema.insert(construct_exclude_field(resource.id_field, 
                {field.name: field}, request.schema.get('exclude')), overwrite=True)

    if 'query' in resource.requests:
        request = resource.requests['query']
        request.responses[OK].schema.structure['resources'].item.insert(field)

        request.schema.insert(construct_fields_field({field.name: field},
            request.schema.get('fields')), overwrite=True)

        if field.deferred:
            request.schema.insert(construct_include_field({field.name: field},
                request.schema.get('include')), overwrite=True)
        else:
            request.schema.insert(construct_exclude_field(resource.id_field,
                {field.name: field}, request.schema.get('exclude')), overwrite=True)

        if field.operators:
            for operator in OperatorConstructor.construct({}, field).itervalues():
                request.schema.structure['query'].insert(operator)

        if field.sortable:
            tokens = []
            for suffix in ('', '+', '-'):
                tokens.append(field.name + suffix)
            sort = request.schema.structure.get('sort')
            if sort:
                sort.item.redefine_enumeration(tokens)
            else:
                request.schema.structure['sort'] = Sequence(
                    Enumeration(sorted(tokens), nonnull=True),
                        description='The sort order for this query.')

    if field.readonly:
        return

    if 'create' in resource.requests and field.oncreate is not False:
        resource.requests['create'].schema.insert(field)
    if 'update' in resource.requests and field.onupdate is not False:
        resource.requests['update'].schema.insert(field.clone(required=False))
    if 'put' in resource.requests and field.onput is not False:
        resource.requests['put'].schema.insert(field)

def clone_field(field, name=None, description=None):
    return field.clone(name=name, description=description, nonnull=True, default=None,
        required=False, notes=None, readonly=False, deferred=False, sortable=False,
        ignore_null=False, operators=None)

def construct_fields_field(fields, original=None, field_name='fields'):
    if original:
        tokens = list(original.item.enumeration)
    else:
        tokens = []

    tokens.extend(fields.keys())
    return Sequence(Enumeration(sorted(tokens), nonnull=True), 
        name=field_name, unique=True,
        description='The exact fields which should be returned for this query.')

def construct_exclude_field(id_field, fields, original=None, field_name='exclude'):
    if original:
        tokens = list(original.item.enumeration)
    else:
        tokens = []

    for name, field in fields.iteritems():
        if name != id_field.name and not field.deferred:
            tokens.append(name)

    if tokens:
        return Sequence(Enumeration(sorted(tokens), nonnull=True), name=field_name,
            description='Fields which should not be returned for this query.')

def construct_include_field(fields, original=None, field_name='include'):
    if original:
        tokens = list(original.item.enumeration)
    else:
        tokens = []

    for name, field in fields.iteritems():
        if field.deferred:
            tokens.append(name)

    if tokens:
        return Sequence(Enumeration(sorted(tokens), nonnull=True), name=field_name,
            description='Deferred fields which should be returned for this query.')

def construct_returning(resource):
    return Sequence(Enumeration(sorted(resource.schema.keys()), nonnull=True))

def filter_schema_for_response(resource):
    id_field = resource.id_field
    schema = {}
    for name, field in resource.filter_schema(exclusive=False, readonly=True).iteritems():
        if name == id_field.name:
            schema[name] = field.clone(required=True)
        elif field.required:
            schema[name] = field.clone(required=False)
        else:
            schema[name] = field
    return schema

def is_returned(field, request):
    returned = field.returned
    if not returned:
        return False
    if isinstance(returned, basestring):
        returned = returned.split(' ')
    return (request in returned)

def is_returning_supported(resource, declaration):
    supported = False
    if declaration:
        supported = getattr(declaration, 'support_returning', False)
        if supported and RETURNING in resource.schema:
            raise Exception('cannot support returning for this resource')
    return supported

def construct_query_request(resource, declaration=None):
    fields = filter_schema_for_response(resource)
    schema = {
        'fields': construct_fields_field(fields),
        'limit': Integer(minimum=0,
            description='The maximum number of resources to return for this query.'),
        'offset': Integer(minimum=0, default=0,
            description='The offset into the result set of this query.'),
        'total': Boolean(default=False, nonnull=True,
            description='If true, only return the total for this query.'),
    }

    include_field = construct_include_field(fields)
    if include_field:
        schema['include'] = include_field

    exclude_field = construct_exclude_field(resource.id_field, fields)
    if exclude_field:
        schema['exclude'] = exclude_field

    tokens = []
    for name, field in fields.iteritems():
        if field.sortable:
            for suffix in ('', '+', '-'):
                tokens.append(name + suffix)

    if tokens:
        schema['sort'] = Sequence(Enumeration(sorted(tokens), nonnull=True),
            description='The sort order for this query.')

    operators = {}
    for name, field in fields.iteritems():
        if field.operators:
            OperatorConstructor.construct(operators, field)

    if declaration:
        additions = getattr(declaration, 'operators', None)
        if additions:
            operators.update(additions)

    if operators:
        schema['query'] = Structure(operators,
            description='The query to filter resources by.')

    response_schema = Structure({
        'total': Integer(nonnull=True, minimum=0,
            description='The total number of resources in the result set for this query.'),
        'resources': Sequence(Structure(fields), nonnull=True),
    })

    valid_responses = [OK]
    if declaration:
        valid_responses = getattr(declaration, 'valid_responses', valid_responses)

    responses = {INVALID: Response(Errors)}
    for response_code in valid_responses:
        responses[response_code] = Response(response_schema)

    return Request(
        name = 'query',
        endpoint = (GET, resource.name),
        auto_constructed = True,
        resource = resource,
        title = 'Querying %s' % pluralize(resource.title.lower()),
        schema = Structure(schema),
        responses = responses,
    )

def construct_get_request(resource, declaration=None):
    fields = filter_schema_for_response(resource)
    schema = {'fields': construct_fields_field(fields)}

    include_field = construct_include_field(fields)
    if include_field:
        schema['include'] = include_field

    exclude_field = construct_exclude_field(resource.id_field, fields)
    if exclude_field:
        schema['exclude'] = exclude_field

    response_schema = Structure(fields)
    return Request(
        name = 'get',
        endpoint = (GET, resource.name + '/id'),
        specific = True,
        auto_constructed = True,
        resource = resource,
        title = 'Getting a specific %s' % resource.title.lower(),
        schema = schema and Structure(schema) or None,
        responses = {
            OK: Response(response_schema),
            INVALID: Response(Errors),
        }
    )

def construct_create_request(resource, declaration=None):
    resource_schema = {}
    for name, field in resource.filter_schema(exclusive=False, readonly=False).iteritems():
        if field.is_identifier:
            if field.oncreate is True:
                resource_schema[name] = field.clone(ignore_null=True)
        elif field.oncreate is not False:
            resource_schema[name] = field

    support_returning = is_returning_supported(resource, declaration)
    if support_returning:
        resource_schema[RETURNING] = construct_returning(resource)

    response_schema = {}
    for name, field in resource.schema.iteritems():
        if field.is_identifier or is_returned(field, 'create'):
            response_schema[name] = field.clone(required=True)
        elif support_returning:
            response_schema[name] = field.clone(required=False)
    
    return Request(
        name = 'create',
        endpoint = (POST, resource.name),
        auto_constructed = True,
        resource = resource,
        title = 'Creating a new %s' % resource.title.lower(),
        schema = Structure(resource_schema, name='resource'),
        responses = {
            OK: Response(Structure(response_schema)),
            INVALID: Response(Errors),
        }
    )

def construct_load_request(resource, declaration=None):
    fields = filter_schema_for_response(resource)
    response_schema = Sequence(Structure(fields), nonnull=True)

    schema = {
        'fields': construct_fields_field(fields),
        'identifiers': Sequence(resource.id_field.clone(), nonempty=True),
    }

    include_field = construct_include_field(fields)
    if include_field:
        schema['include'] = include_field

    return Request(
        name = 'load',
        endpoint = (LOAD, resource.name),
        auto_constructed = True,
        resource = resource,
        title = 'Loading %s' % pluralize(resource.title.lower()),
        schema = Structure(schema),
        responses = {
            OK: Response(response_schema),
            INVALID: Response(Errors),
        }
    )

def construct_put_request(resource, declaration=None):
    resource_schema = {}
    for name, field in resource.filter_schema(exclusive=False, readonly=False).iteritems():
        if not field.is_identifier and field.onput is not False:
            resource_schema[name] = field

    support_returning = is_returning_supported(resource, declaration)
    if support_returning:
        resource_schema[RETURNING] = construct_returning(resource)

    response_schema = {}
    for name, field in resource.schema.iteritems():
        if field.is_identifier or is_returned(field, 'put'):
            response_schema[name] = field.clone(required=True)
        elif support_returning:
            response_schema[name] = field.clone(required=False)

    return Request(
        name = 'put',
        endpoint = (PUT, resource.name + '/id'),
        specific = True,
        auto_constructed = True,
        subject_required = False,
        resource = resource,
        title = 'Putting a specific %s' % resource.title.lower(),
        schema = Structure(resource_schema),
        responses = {
            OK: Response(Structure(response_schema)),
            INVALID: Response(Errors),
        }
    )

def construct_update_request(resource, declaration=None):
    resource_schema = {}
    for name, field in resource.filter_schema(exclusive=False, readonly=False).iteritems():
        if not field.is_identifier and field.onupdate is not False:
            if field.required:
                field = field.clone(required=False)
            resource_schema[name] = field

    support_returning = is_returning_supported(resource, declaration)
    if support_returning:
        resource_schema[RETURNING] = construct_returning(resource)

    response_schema = {}
    for name, field in resource.schema.iteritems():
        if field.is_identifier or is_returned(field, 'update'):
            response_schema[name] = field.clone(required=True)
        elif support_returning:
            response_schema[name] = field.clone(required=False)

    valid_responses = [OK]
    if declaration:
        valid_responses = getattr(declaration, 'valid_responses', valid_responses)

    responses = {INVALID: Response(Errors)}
    for response_code in valid_responses:
        responses[response_code] = Response(Structure(response_schema))

    return Request(
        name = 'update',
        endpoint = (POST, resource.name + '/id'),
        specific = True,
        auto_constructed = True,
        resource = resource,
        title = 'Updating a specific %s' % resource.title.lower(),
        schema = Structure(resource_schema),
        responses = responses,
    )

def construct_create_update_request(resource, declaration=None):
    schema = {}
    for name, field in resource.filter_schema(exclusive=False, readonly=False).iteritems():
        if field.required:
            field = field.clone(required=False)
        schema[name] = field

    schema = Sequence(Structure(schema))
    response_schema = Sequence(Structure({
        resource.id_field.name: resource.id_field.clone(required=True),
    }))

    return Request(
        name = 'create_update',
        endpoint = (PUT, resource.name),
        specific = False,
        auto_constructed = True,
        resource = resource,
        title = 'Creating and updating multiple %s' % pluralize(resource.title.lower()),
        schema = schema,
        responses = {
            OK: Response(response_schema),
            INVALID: Response(Errors),
        }
    )

def construct_delete_request(resource, declaration=None):
    id_field = resource.id_field
    response_schema = Structure({
        id_field.name: id_field.clone(required=True)
    })

    valid_responses = [OK]
    if declaration:
        valid_responses = getattr(declaration, 'valid_responses', valid_responses)

    responses = {INVALID: Response(Errors)}
    for response_code in valid_responses:
        responses[response_code] = Response(response_schema)

    return Request(
        name = 'delete',
        endpoint = (DELETE, resource.name + '/id'),
        specific = True,
        auto_constructed = True,
        resource = resource,
        title = 'Deleting a specific %s' % resource.title.lower(),
        schema = None,
        responses = responses,
    )

DEFAULT_REQUESTS = ['create', 'delete', 'get', 'query', 'update']
STANDARD_REQUESTS = {
    'create': construct_create_request,
    'create_update': construct_create_update_request,
    'delete': construct_delete_request,
    'get': construct_get_request,
    'load': construct_load_request,
    'put': construct_put_request,
    'query': construct_query_request,
    'update': construct_update_request,
}
VALIDATED_REQUESTS = ['create', 'put', 'update']
