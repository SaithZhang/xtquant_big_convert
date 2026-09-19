# ASCII only. Appended to the unmodified upstream package entry at build time.
def init(ContextInfo):
    strategy = _runtime._strategy_module
    rpc = dict(strategy._config.get("rpc") or {})
    rpc["warm_context_data"] = False
    strategy.configure(rpc=rpc)
    result = _runtime.init(ContextInfo)
    if strategy._rpc_service is None:
        raise RuntimeError("Galaxy Redis RPC did not start; inspect QMT log")
    print("[GalaxyPackage] ready transport=redis orders=False commit=" + GALAXY_SOURCE_COMMIT)
    return result


def stop(ContextInfo):
    _runtime.reset_app()
    print("[GalaxyPackage] stopped")
