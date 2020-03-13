class Autoscaling:
    def __init__(self, threshold_growing=None, threshold_shrinking=None, ratio_growing=None, ratio_shrinking = None):
        self.threshold_growing = threshold_growing
        self.threshold_shrinking = threshold_shrinking
        self.ratio_growing = ratio_growing
        self.ratio_shrinking = ratio_shrinking

