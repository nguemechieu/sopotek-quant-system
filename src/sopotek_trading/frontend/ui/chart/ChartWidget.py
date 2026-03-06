import numpy as np
import pyqtgraph as pg

from PySide6 import QtCore
from PySide6.QtWidgets import QTabWidget
from pyqtgraph import (
    GraphicsLayoutWidget,
    InfiniteLine,
    TextItem,
    SignalProxy,
    mkPen
)

from sopotek_trading.frontend.ui.chart.chart_items import CandlestickItem


class ChartWidget(GraphicsLayoutWidget):

    sigMouseMoved = QtCore.Signal(object)

    def __init__(self, symbol, timeframe, controller):

        super().__init__()

        self.chart_tabs =QTabWidget()
        self.symbol = symbol
        self.timeframe = timeframe
        self.controller = controller

        self.setBackground("#0d1117")

        pg.setConfigOptions(
            antialias=True,
            useOpenGL=True
        )

        # ======================================================
        # PRICE CHART
        # ======================================================

        self.price_plot = self.addPlot(row=0, col=0)

        self.price_plot.showGrid(x=True, y=True)
        self.price_plot.setLabel("left", "Price")
        self.price_plot.setLabel("bottom", "Time")

        self.price_plot.setMouseEnabled(x=True, y=False)

        # Candles
        self.candle_item = CandlestickItem()
        self.price_plot.addItem(self.candle_item)

        # EMA
        self.ema_curve = self.price_plot.plot(
            pen=mkPen("#FFD700", width=2)
        )

        # Trade markers
        self.trade_markers = pg.ScatterPlotItem()
        self.price_plot.addItem(self.trade_markers)

        # ======================================================
        # VOLUME
        # ======================================================

        self.volume_plot = self.addPlot(row=1, col=0)

        self.volume_plot.setXLink(self.price_plot)

        self.volume_bars = pg.BarGraphItem(
            x=[],
            height=[],
            width=0.6
        )

        self.volume_plot.addItem(self.volume_bars)

        # ======================================================
        # RSI
        # ======================================================

        self.rsi_plot = self.addPlot(row=2, col=0)

        self.rsi_plot.setXLink(self.price_plot)

        self.rsi_curve = self.rsi_plot.plot(
            pen=mkPen("#00FFFF", width=2)
        )

        self.rsi_plot.addLine(y=70, pen=mkPen("red"))
        self.rsi_plot.addLine(y=30, pen=mkPen("green"))

        # ======================================================
        # CROSSHAIR
        # ======================================================

        self.v_line = InfiniteLine(angle=90, movable=False)
        self.h_line = InfiniteLine(angle=0, movable=False)

        self.price_plot.addItem(self.v_line, ignoreBounds=True)
        self.price_plot.addItem(self.h_line, ignoreBounds=True)

        self.text = TextItem(color="w")
        self.price_plot.addItem(self.text)

        self.proxy = SignalProxy(
            self.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._mouse_moved
        )

        # Layout proportions
        self.ci.layout.setRowStretchFactor(0, 25)
        self.ci.layout.setRowStretchFactor(1, 5)
        self.ci.layout.setRowStretchFactor(2, 5)

    # ======================================================
    # CROSSHAIR
    # ======================================================

    def _mouse_moved(self, evt):

        pos = evt[0]

        if self.price_plot.sceneBoundingRect().contains(pos):

            mouse_point = self.price_plot.vb.mapSceneToView(pos)

            x = mouse_point.x()
            y = mouse_point.y()

            self.v_line.setPos(x)
            self.h_line.setPos(y)

            self.text.setHtml(
                f"<span style='color:white'>Price: {y:.4f}</span>"
            )

            self.text.setPos(x, y)

    # ======================================================
    # UPDATE CANDLES
    # ======================================================

    def update_candles(self, df):

        if df is None or len(df) == 0:
            return

        x = np.arange(len(df))

        candles = np.column_stack([
            x,
            df["open"].values,
            df["close"].values,
            df["low"].values,
            df["high"].values
        ])

        self.controller.candles=candles

        # EMA
        ema = df["close"].ewm(span=21).mean()

        self.ema_curve.setData(x, ema)

        # Volume
        self.volume_bars.setOpts(
            x=x,
            height=df["volume"].values
        )

        # RSI
        rsi = self._compute_rsi(df["close"])

        self.rsi_curve.setData(x, rsi)

        self.price_plot.enableAutoRange()

    # ======================================================
    # RSI
    # ======================================================

    def _compute_rsi(self, series, period=14):

        delta = series.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / avg_loss

        rsi = 100 - (100 / (1 + rs))

        return rsi

    def link_all_charts(self,count):
        charts = []
        for i in range(count):
            widget = self.chart_tabs.widget(i)
            if isinstance(widget, ChartWidget): charts.append(widget)
            if len(charts) < 2:
                return
            base = charts[0]
            for chart in charts[1:]: chart.link_to(base)

    def update_orderbook_heatmap(self, bids, asks):
        pass
