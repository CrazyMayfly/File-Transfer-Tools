from tqdm import tqdm


class PbarManager:
    def __init__(self, pbar: tqdm):
        self.__pbar = pbar
        self.__lock = self.__pbar.get_lock()

    def update(self, size: int, decrease=False):
        with self.__lock:
            if not decrease:
                self.__pbar.update(size)
            else:
                self.__pbar.total -= size

    def set_status(self, fail: bool):
        self.__pbar.colour = '#F44336' if fail else '#98c379'
        self.__pbar.close()
