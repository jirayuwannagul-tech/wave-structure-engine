def test_import_core_modules():
    import data.market_data_fetcher
    import data.candle_utils

    import analysis.pivot_detector
    import analysis.swing_builder
    import analysis.wave_degree
    import analysis.wave_detector
    import analysis.corrective_detector
    import analysis.rule_validator
    import analysis.fibonacci_engine
    import analysis.key_levels
    import analysis.wave_position
    import analysis.future_projection
    import analysis.main_alternate_count

    import scenarios.scenario_engine

    import monitor.price_confirmation
    import monitor.breakout_detector
    import monitor.rejection_detector
    import monitor.mtf_alignment
    import monitor.market_context

    import output.report_formatter
    import output.daily_report

    import alerts.notifier
    import scheduler.daily_scheduler
    import core.engine
    import services.news_rss_monitor

    assert True
