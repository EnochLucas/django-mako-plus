.. _tutorial_css_js:

T4: zip(HTML, JS, CSS)
===========================================

.. contents::
    :depth: 2

Modern web pages are made up of three primary parts: HTML, CSS, and Javascript (media might be a fourth, but we'll go with three for now). Since all of your pages need these three components, this framework combines them intelligently for you. All you have to do is name the .html, the css., and the .js files correctly, and DMP will insert the ``<link>`` and ``<script>`` tags automatically for you.

Convention over configuration.  Just like a slice of home-baked apple pie.

    If you are using a bundler like `webpack <https://webpack.js.org/>`_, be sure to read `JS Bundling with Webpack <static_webpack.html>`_.


A Bit of Style
---------------------------------------------------

To style our index.html file, open ``homepage/styles/index.css`` and copy the following into it:

.. code-block:: python

    .server-time {
        font-size: 2em;
        color: red;
    }

When you refresh your page, the server time should be styled with large, red text. If you view the html source in your browser, you'll see a new ``<link...>`` near the top of your file. It's as easy as naming the files the same and placing the .css file in the styles/ directory.

The framework knows how to follow template inheritance. For example, since ``index.html`` extends from ``base.htm``, we can actually put our CSS in **either**: ``index.css`` or ``base.css``.  Place your CSS styles in the appropriate file, depending on where the HTML elements are located. For example, let's style our header a little. Since the ``<header>`` element is in ``base.htm``, open ``homepage/styles/base.css`` and check for the following:

.. code:: css

    html, body {
        margin: 0;
        padding: 0;
    }

    header {
        background-color: #147871;
        padding: 15px 20px;
        border-top: 4px solid #606060;
        border-bottom: 4px solid #606060;
    }

    header h1 {
        color: #FFFFFF;
        margin: 0;
        padding: 0;
    }

    main {
        margin: 0;
        padding: 15px;
    }

Since base.htm will be the parent page of nearly every HTML page on your site, these common styles will apply to all pages. If you view source in the browser, you'll see the CSS files were included as follows:

.. code-block:: html+mako

    <link rel="stylesheet" type="text/css" href="/static/homepage/styles/base.css?v=5a8931aee4c59dee" />
    <link rel="stylesheet" type="text/css" href="/static/homepage/styles/index.css?v=5aac6c929d3401a1" />

Note that ``base.css`` is included first because it's at the top of the hierarchy. Styles from ``index.css`` override any conflicting styles from ``base.css``, which makes sense because ``index.html`` is the final template in the inheritance chain.

    You might be wondering about ``?v=5a8931aee4c59dee`` in the link.  That's the file modification time and content checksum for the file. This is included because browsers don't automatically download new static files. They use their cached versions until a specified date, often far in the future. By adding a number to the end of the file, browsers think the CSS files are "new" because the "filename" changes whenever you change the file.  Trixy browserses...


Javascript
-----------------------------

Javascript files work the same way as CSS files, so if you skipped the CSS sections above, you might want to go read through them. Javascript files are placed in the ``scripts/`` directory and, of course, end with ``*.js`` extension.

Let's add a client-side, Javascript-based timer. Create the file ``homepage/scripts/index.js`` and place the following JQuery code into it:

.. code-block:: javascript

    $(function() {
        // update the time every 1 seconds
        window.setInterval(function() {
            $('.browser-time').text('The current browser time is ' + new Date() + '.');
        }, 1000);
    });

Refresh your browser page, and you should see the browser time updating each second. Congratulations, you've now got a modern, HTML5 web page.

Javascript in Context
--------------------------------

What if we need to get a value from our Python view code, such as the server time, into the ``index.js`` file?  DMP handles this too.

Lets compare the server time with the browser time allows us to calculate the time zone difference between the two. To send a variable to the JS environment, tag it with ``jscontext()``.  Change your ``index.py`` file to the following:

.. code-block:: python

    from django.conf import settings
    from django_mako_plus import view_function, jscontext
    from datetime import datetime

    @view_function
    def process_request(request):
        context = {
            jscontext('now'): datetime.now(),
        }
        return request.dmp.render('index.html', context)

Reload your browser, and then right-click and "Inspect" to see your DOM.  The ``<script>`` tag now looks like this:

::

    <script type="text/javascript" src="/static/homepage/scripts/index.js?1509480811" data-context="u5a8240023befacbc327df447012720"></script>

When you tag a context key with ``jscontext('now')``, DMP adds it to a context object and connects it via ``data-context``.  Note that variables sent via ``jscontext`` must be serializable by Django's ``django.core.serializers.json.DjangoJSONEncoder`` (although you can set a custom encoder if needed).  The default encoder includes all the typical types, plus datetime, date, time, timedelta, Decimal, and UUID.

Let's use the variable in ``index.js``.  Note this example uses a ``jQuery`` ready function, but `regular JS works too <static_context.html#referencing-the-context>`_.

.. code-block:: javascript

    $(function(context) {
        return function() {
            console.log(context)
            var serverTime = new Date(context.now)   // server time (from DMP_CONTEXT)
            var browserTime = new Date()             // browser time
            var hours = Math.round(Math.abs(serverTime - browserTime) / 36e5)
            $('.browser-time').text('The current browser is ' + hours + ' hours off of the server time zone.')
        }
    }(DMP_CONTEXT.get()))

Reload your browser, and you should see the calculation of hours.

    The context is sent to the script via a data attribute on the ``<script>`` element.  The closure surrounding everything keeps the variable local to this script.  `Read more about this <static_webpack.html#examples>`_.



Bundlers like Webpack, Browserify, etc.
------------------------------------------

If you are using JS bundles, DMP fits right in.  See bundling in `JS Bundling with Webpack <static_webpack.html>`_ for more information.


Behind the CSS and JS Curtain
-----------------------------

After reading about automatic CSS and JS inclusion, you might want to know how it works. It's all done in the templates (base.htm now, and base\_ajax.htm in a later section below) you are inheriting from. Open ``base.htm`` and look at the following code:

::

    ## render the static file links for this template
    <script src="/django_mako_plus/dmp-common.min.js"></script>
    ${ django_mako_plus.links(self) }

The calls to ``links(self)`` include the ``<link>`` and ``<script>`` tags for the template name and all of its supertemplates. These links are placed at the end of your ``<head>`` section.  (Just a few years ago, common practice was to place script tags at the end of the body, but modern browsers with asyncronous and deferred scripts have put them back in the body.)

This all works because the ``index.html`` template extends from the ``base.htm`` template. If you fail to inherit from ``base.htm`` or ``base_ajax.htm``, DMP won't be able to include the support files.

Read more about providers in `Rendering CSS and JS <static.html>`_.
