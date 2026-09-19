# ASCII only; appended to upstream's GBK single-file bundle, not run standalone.
# The embedded runtime has already applied the shell configuration here.
_galaxy_extra = _runtime.capture_qmt_injected_funcs(globals())
if not callable(_galaxy_extra.get("down_history_data")):
    if callable(globals().get("download_history_data")):
        _galaxy_extra["down_history_data"] = globals()["download_history_data"]
_runtime.bind_runtime_api(extra_funcs=_galaxy_extra)


def init(ContextInfo):
    # Upstream defaults to a background ContextInfo warmup. Keep every request
    # and warmup on QMT callbacks in this Galaxy deployment.
    strategy = _runtime._strategy_module
    rpc = dict(strategy._config.get("rpc") or {})
    rpc["warm_context_data"] = False
    strategy.configure(rpc=rpc)
    result = _runtime.init(ContextInfo)
    if strategy._rpc_service is None:
        raise RuntimeError("Galaxy bridge RPC failed to start; inspect QMT log")
    print("[GalaxySim] ready RPC=127.0.0.1:18689 push=127.0.0.1:18690 orders=%s" %
          BIGQMT_REDIS_CONFIG["rpc_allow_order_methods"])
    return result


def stop(ContextInfo):
    _runtime.reset_app()
    print("[GalaxySim] stopped")
