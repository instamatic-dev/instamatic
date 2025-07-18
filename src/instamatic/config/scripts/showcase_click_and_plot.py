from __future__ import annotations

from contextlib import nullcontext
from threading import Event

from matplotlib import pyplot as plt

global _ctrl


figure_is_displayed = Event()

vertex_figure = None
vertex_list: list[tuple[int, int]] = []
showcase_done = False
print(dir(_ctrl.cam))
# can't be done: have access to controller.ctrl only, not controller with .app.
stream = _ctrl.app.get_module('stream')


def collect_vertex(click_event):
    global showcase_done, vertex_figure, vertex_list
    if figure_is_displayed.is_set():
        vertex_list = []
        figure_is_displayed.clear()
    else:
        if click_event.button == 1:
            xy = (click_event.x, click_event.y)
            stream.processor.draw.circle(xy, radius=2, fill='red')
            if vertex_list:
                last_xy = vertex_list[-1]
                stream.processor.draw.line([xy, last_xy], width=2, fill='red')
            vertex_list.append(xy)
        else:
            if not vertex_list:
                showcase_done = True
                return
            vertex_figure, ax1 = plt.subplots()
            ax2 = ax1.twinx()
            ax1.set_xlabel('click')
            ax1.set_ylabel('X [pixels]')
            ax2.set_ylabel('Y [pixels]')
            ax1.yaxis.label.set_color('red')
            ax2.yaxis.label.set_color('blue')
            ax2.spines['left'].set_color('red')
            ax2.spines['right'].set_color('blue')
            ax1.tick_params(axis='y', colors='red')
            ax2.tick_params(axis='y', colors='blue')
            ax1.plot([v[0] for v in vertex_list], color='red', label='X')
            ax2.plot([v[1] for v in vertex_list], color='blue', label='Y')


print('Start of script showcase_click_and_plot.py')
print('Start of script showcase_click_and_plot.py')

vertex_tracer = stream.click_dispatcher.add_listener('vertex_tracer', collect_vertex)

while not showcase_done:
    with vertex_tracer as vt:
        with stream.processor.temporary_figure(f) if (f := vertex_figure) else nullcontext:
            vt.get_click()

print('End of script showcase_click_and_plot.py')
