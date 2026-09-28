import inspect
from starlette.templating import Jinja2Templates

class CompatibleJinja2Templates(Jinja2Templates):
    """
    Ensures TemplateResponse works seamlessly across all versions of Starlette:
    - Legacy Starlette (< 0.36): TemplateResponse(name, context)
    - Modern Starlette (>= 0.36): TemplateResponse(request, name, context) or keyword args
    """
    def TemplateResponse(self, *args, **kwargs):
        sig = inspect.signature(super().TemplateResponse)
        first_param = list(sig.parameters.keys())[0] if sig.parameters else None

        name = kwargs.get('name')
        context = kwargs.get('context', {})
        request = kwargs.get('request')

        if args:
            if isinstance(args[0], str):
                name = args[0]
                if len(args) > 1 and isinstance(args[1], dict):
                    context = args[1]
            elif hasattr(args[0], 'headers') or hasattr(args[0], 'scope'):
                request = args[0]
                if len(args) > 1:
                    name = args[1]
                if len(args) > 2 and isinstance(args[2], dict):
                    context = args[2]

        if not request and isinstance(context, dict):
            request = context.get('request')
        if not isinstance(context, dict):
            context = {}
        if request and 'request' not in context:
            context['request'] = request

        status_code = kwargs.get('status_code', 200)
        headers = kwargs.get('headers')
        media_type = kwargs.get('media_type')
        background = kwargs.get('background')

        call_kwargs = {}
        if headers is not None:
            call_kwargs['headers'] = headers
        if media_type is not None:
            call_kwargs['media_type'] = media_type
        if background is not None:
            call_kwargs['background'] = background

        if first_param == 'request':
            return super().TemplateResponse(request, name, context, status_code=status_code, **call_kwargs)
        else:
            return super().TemplateResponse(name, context, status_code=status_code, **call_kwargs)

templates = CompatibleJinja2Templates(directory="templates")
