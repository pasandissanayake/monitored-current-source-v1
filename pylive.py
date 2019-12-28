import matplotlib.pyplot as plt
import numpy as np
import time

class plot:
    def __init__(self, x_vec, y_vec, x_label, y_label, title):
        self.x_label = x_label
        self.y_label = y_label
        self.title = title

        self.exists = True
        self.fig = plt.figure(figsize=(6, 4))
        self.ax = self.fig.add_subplot(111)

        self.ax.set_xlabel(x_label)
        self.ax.set_ylabel(y_label)
        self.ax.set_title(title)

        self.line, = self.ax.plot(x_vec, y_vec, 'b-', alpha=1, linewidth=0.7)
        self.fig.canvas.mpl_connect('close_event', self.handle_close)

        plt.grid(b=True, which='major', color='#666666', linestyle='-')
        plt.minorticks_on()
        plt.grid(b=True, which='minor', color='#999999', linestyle='-', alpha=0.2)
        plt.autoscale(True, tight=False)
        plt.ion()

        self.fig.show()

    def live_plot(self, x_vec, y_vec):
        try:
            if self.exists:
                self.line.set_xdata(x_vec)
                self.line.set_ydata(y_vec)
                if np.min(y_vec) - np.std(y_vec) == np.max(y_vec) + np.std(y_vec):
                    self.ax.set_ylim([np.min(y_vec) - 5, np.max(y_vec) + 5])
                else:
                    self.ax.set_ylim([min(max(np.min(y_vec) - np.std(y_vec), 0), max(np.min(y_vec) - (np.max(y_vec) - np.min(y_vec))*5, 0)),max(np.max(y_vec) + np.std(y_vec), np.max(y_vec) + (np.max(y_vec) - np.min(y_vec))*5)])
                self.fig.canvas.flush_events()
                time.sleep(0.001)
                return self.exists
        except Exception as e:
            print(e)
            plt.close(self.fig)
            time.sleep(0.01)
            self.exists = False
            return self.exists

    def is_existing(self):
        return self.exists

    def handle_close(self, evt):
        self.exists = False

    def restart(self, x_vec, y_vec):
        self.__init__(x_vec,y_vec,self.x_label,self.y_label,self.title)

    def terminate(self):
        plt.close(self.fig)



''' 
    Usage example
    -------------

size = 100
x_vec = np.linspace(-1, 0, size + 1)[0:-1]
y_vec = np.random.randn(len(x_vec))
z_vec = np.random.randn(len(x_vec))

k = 0
a = plot(x_vec, y_vec, 'aa', 'bb', 'cc')
b = plot(x_vec, z_vec, 'pp', 'qq', 'rr')
while True:
    rand_val = np.random.rand(1)
    y_vec[-1] = k
    z_vec[-1] = k/10
    if a.is_existing(): a.live_plot(x_vec,y_vec)
    if b.is_existing(): b.live_plot(x_vec,z_vec)
    y_vec = np.append(y_vec[1:],0.0)
    z_vec = np.append(z_vec[1:],0.0)
    if k<1000: k += 100
    else: k += -100


'''