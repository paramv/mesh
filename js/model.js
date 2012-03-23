define([
    'vendor/underscore',
    'vendor/jquery',
    'vendor/json2',
    'class',
    'events',
    'fields',
    'mesh'
], function(_, $, json2, Class, Eventful, fields, mesh) {
    var isArray = _.isArray, isBoolean = _.isBoolean, isEqual = _.isEqual, isString = _.isString;

    var Request = Class.extend({
        ajax: $ajax,
        path_expr: /\/id(?=\/|$)/,

        init: function(params) {
            var url;
            this.bundle = params.bundle;
            this.cache = [];
            this.method = params.method;
            this.mimetype = params.mimetype;
            this.name = params.name;
            this.path = params.path;
            this.responses = params.responses;
            this.schema = params.schema;

            this.url = this.path;
            if (mesh && mesh.bundles) {
                url = mesh.bundles[this.bundle];
                if (url) {
                    this.url = url + this.path;
                }
            }
        },
        
        initiate: function(id, data) {
            var self = this, cache = this.cache, url = this.url,
                signature, cached, params, deferred;

            if (id != null) {
                url = url.replace(self.path_expr, '/' + id);
            }

            signature = [url, data];
            for (var i = 0, l = cache.length; i < l; i++) {
                cached = cache[i];
                if (isEqual(cached[0], signature)) {
                    return cached[1];
                }
            }

            params = {
                contentType: this.mimetype,
                dataType: 'json',
                type: this.method,
                url: url
            };

            deferred = $.Deferred();
            cached = [signature, deferred];

            if (data) {
                if (!isString(data)) {
                    if (this.schema != null) {
                        try {
                            data = this.schema.serialize(data, this.mimetype);
                        } catch (error) {
                            if (error instanceof fields.ValidationError) {
                                return deferred.reject();
                            } else {
                                throw error;
                            }
                        }
                    } else {
                        data = null;
                    }
                    if (data && this.mimetype === 'application/json') {
                        data = JSON.stringify(data);
                        params.processData = false;
                    }
                }
                params.data = data;
            }

            params.success = function(data, status, xhr) {
                var response;
                cache.splice(_.indexOf(cache, cached), 1);

                response = self.responses[xhr.status];
                if (response) {
                    try {
                        data = response.schema.unserialize(data, response.mimetype);
                    } catch (error) {
                        if (error instanceof fields.ValidationError) {
                            deferred.reject();
                        } else {
                            throw error;
                        }
                    }
                }
                deferred.resolve(data, xhr);
            };

            params.error = function(xhr) {
                var error = null, mimetype;
                cache.splice(_.indexOf(cache, cached), 1);

                mimetype = xhr.getResponseHeader('content-type');
                if (mimetype && mimetype.substr(0, 16) === 'application/json') {
                    error = $.parseJSON(xhr.responseText);
                }
                deferred.reject(error, xhr);
            };

            cache.push(cached);
            self.ajax(params);
            return deferred;
        }
    });

    var Manager = Eventful.extend({
        init: function(model) {
            this.cache = [];
            this.model = model;
            this.models = {};
        },

        associate: function(model) {
            var id = model.id || model.cid;
            if (this.models[id]) {
                if (this.models[id] !== model) {
                    var name = this.model.prototype.__name__;
                    throw new Error('attempt to associate duplicate ' + name + ', id = ' + id);
                }
            } else {
                this.models[id] = model;
            }
            return this;
        },

        clear: function() {
            this.cache = [];
            this.models = {};
            return this;
        },

        dissociate: function(model) {
            if (model.id) {
                delete this.models[model.id];
            }
            if (model.cid) {
                delete this.models[model.cid];
            }
            return this;
        },

        get: function(id) {
            var model = this.models[id];
            if (!model) {
                model = this.instantiate({id: id});
            }
            return model;
        },

        instantiate: function(model, loaded) {
            var instance;
            if (model.id) {
                instance = this.models[model.id];
                if (instance) {
                    instance.set(model);
                    if (loaded) {
                        instance._loaded = true;
                    }
                    return instance;
                }
            }
            return this.model(model, this, loaded);
        },

        load: function(id, params) {
            if (_.isNumber(id) || isString(id)) {
                return this.get(id).refresh(params, true);
            } else {
                return this.collection(id).load();
            }
        },

        notify: function(model, event) {
            if (model.id && this.models[model.id]) {
                this.trigger('change', this, model);
            }
        }
    });

    var Collection = Eventful.extend({
        init: function(manager, params) {
            params = params || {};
            this.cache = {};
            this.manager = manager;
            this.models = [];
            this.plain = params.plain;
            this.query = params.query || {};
            this.total = null;
            this.manager.on('change', this.notify, this);
        },

        add: function(models, idx) {
            var self = this, model;
            if (!isArray(models)) {
                models = [models];
            }
            if (idx == null) {
                if (self.total != null) {
                    idx = self.total;
                } else {
                    idx = self.models.length;
                }
            }

            for (var i = 0, l = models.length; i < l; i++) {
                model = models[i];
                this.models.splice(idx + 1, 0, model);
                if (model.id) {
                    this.cache[model.id] = model;
                } else if (model.cid) {
                    this.cache[model.cid] = model;
                }
            }

            this.trigger('update', this);
            return this;
        },

        at: function(idx) {
            return this.models[idx] || null;
        },

        create: function(attrs, params, idx) {
            var self = this, model = this.manager.model(attrs);
            return model.save(params).pipe(function(instance) {
                self.add([instance], idx);
                return instance;
            });
        },

        get: function(id) {
            return this.cache[id] || null;
        },

        load: function(params) {

        },

        notify: function(event, manager, model) {
            var id = model.id || model.cid;
            if (this.cache[id]) {
                this.trigger('change', this, model);
            }
        },

        remove: function(models) {
            var model;
            if (!isArray(models)) {
                models = [models];
            }

            for (var i = 0, l = models.length; i < l; i++) {
                model = models[i];
                this.models.splice(_.indexOf(this.models, model), 1);
                if (model.id) {
                    delete this.cache[model.id];
                }
                if (model.cid) {
                    delete this.cache[model.cid];
                }
            }

            this.trigger('update', this);
            return this;
        },

        reset: function(query) {
            this.cache = {};
            this.models = [];
            this.total = null;
            if (query != null) {
                this.query = query;
            }
            this.trigger('update', this);
            return this;
        }
    });

    var Model = Eventful.extend({
        __new__: function(constructor, base, prototype) {
            constructor.manager = function() {
                return Manager(constructor);
            };
            constructor.models = prototype.__models__ = constructor.manager();
            constructor.collection = function(params, independent) {
                return constructor.models.collection(params, independent);
            };
        },

        __models__: null,
        __name__: null,
        __requests__: null,
        __schema__: null,

        init: function(attrs, manager, loaded) {
            this.cid = null;
            this.id = null;
            this._loaded = loaded;
            this._manager = manager || this.__models__;
            if (attrs != null) {
                this.set(attrs, true);
            }
            if (this.id == null) {
                this.cid = _.uniqueId('_');
            }
            this._manager.associate(this);
        },

        construct: function() {},

        destroy: function(params) {
            var self = this;
            if (self.id == null) {
                self._manager.dissociate(self);
                self.trigger('destroy', self);
                return $.Deferred().resolve();
            }
            return self._initiateRequest('delete', params).done(function(response) {
                self._manager.dissociate(self);
                self.trigger('destroy', self, response);
                return response;
            });
        },

        has: function(attr) {
            var value = this[attr];
            return (value !== undefined && value !== null);
        },

        html: function(attr, fallback) {
            var value = this[attr];
            if (value == null) {
                value = (fallback || '');
            }
            return _.escape('' + value);
        },

        refresh: function(params, conditional) {
            var self = this;
            if (isBoolean(params)) {
                conditional = params;
                params = null;
            } else if (params != null) {
                conditional = false;
            }
            if (self.id == null || (self._loaded && conditional)) {
                return $.Deferred().resolve(self);
            }
            return self._initiateRequest('get', params).pipe(function(data) {
                self.set(data);
                self._loaded = true;
                return self;
            });
        },

        save: function(params) {
            var self = this, creating = (this.id == null), request, data;
            request = self._getRequest(creating ? 'create' : 'update');

            data = request.extract(self);
            if (params != null) {
                $.extend(true, data, params);
            }

            return request.initiate(self.id, data).pipe(function(data) {
                if (creating) {
                    self._manager.associate(self);
                }
                self.set(data);
                self._loaded = true;
                return self;
            });
        },

        set: function(attr, value, silent) {
            var attrs, changing, changed, name, currentValue;
            if (attr != null) {
                if (isString(attr)) {
                    attrs = {};
                    attrs[attr] = value;
                } else {
                    attrs = attr;
                    silent = value;
                }
            } else {
                return this;
            }

            changing = this._currentlyChanging;
            this._currentChanging = true;

            changed = false;
            for (name in attrs) {
                if (attrs.hasOwnProperty(name)) {
                    currentValue = this[name];
                    value = attrs[name];
                    if (!isEqual(value, currentValue)) {
                        changed = changed || {};
                        changed[name] = true;
                        this[name] = value;
                    }
                }
            }

            if (!changing && changed) {
                this.construct();
                if (!silent) {
                    this.trigger('change', this, changed);
                    this._manager.notify(this, 'change');
                }
            }

            this._currentlyChanging = false;
            return this;
        },
    
        _getRequest: function(name) {
            return this.__requests__[name];
        },

        _initiateRequest: function(name, params) {
            return this._getRequest(name).initiate(this.id, params);
        }
    });

    return {
        Collection: Collection,
        Manager: Manager,
        Model: Model,
        Request: Request
    };
});
