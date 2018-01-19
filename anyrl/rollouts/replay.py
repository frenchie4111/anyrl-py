"""
Various replay buffer implementations.
"""

from abc import ABC, abstractmethod, abstractproperty
import random

import numpy as np

class ReplayBuffer(ABC):
    """
    A generic experience replay buffer.

    Replay buffers are useful for off-policy algorithms
    like DQN.
    """
    @abstractproperty
    def size(self):
        """
        Get the current number of transitions stored in
        the buffer.
        """
        pass

    @abstractmethod
    def sample(self, num_samples):
        """
        Sample a batch of experience from the buffer.

        Args:
          num_samples: the number of steps to sample.
            There must be at least num_samples entries in
            the buffer.

        Returns:
          A sequence of num_samples transition dicts.

        Each transition dict should have these keys:
          'obs': the starting observation.
          'action': the chosen action.
          'reward': the reward after taking the action.
          'new_obs': the new observation, or None if the
            episode terminates after this transition.
          'steps': the number of steps bridging the start
            and end observations. For n-step Q-learning,
            this is n.
          'weight': an importance-sampling weight for the
            sample, possibly relative to the rest of the
            samples in the batch.
          'id': (optional) a way to identify the sample
            for update_weights(). This is specific to the
            buffer implementation. This only remains valid
            until the buffer is modified in some way.
        """
        pass

    @abstractmethod
    def add_sample(self, sample, init_weight=None):
        """
        Add a sampled transition to the buffer.

        Args:
          sample: a transition dict similar to the one
            returned by sample(), except that this dict
            shouldn't have an 'id' or 'weight' field.
          init_weight: an initial sampling weight for
            the transition. This is related to the weights
            passed to update_weights().
        """
        pass

    def update_weights(self, samples, new_weights):
        """
        Provide the replay buffer with weights for some
        previously-sampled transitions.

        Args:
          samples: a sequence of transitions returned by a
            previous call to sample(). The buffer must not
            have been modified since the transitions were
            sampled.
          new_weights: a sequence of weights, one per
            sample, indicating something like the loss of
            each sample. The exact meaning is specific to
            the replay buffer implementation.

        Some buffer implementations may choose to
        completely ignore this method.
        """
        pass

class UniformReplayBuffer(ReplayBuffer):
    """
    The simplest possible replay buffer.

    Samples are drawn uniformly, and the buffer is kept to
    a certain size by pruning the oldest samples.
    """
    def __init__(self, capacity):
        self.capacity = capacity
        self.transitions = []

    @property
    def size(self):
        return len(self.transitions)

    def sample(self, num_samples):
        res = [x.copy() for x in random.sample(self.transitions, num_samples)]
        for transition in res:
            transition['weight'] = 1
        return res

    def add_sample(self, sample, init_weight=None):
        self.transitions.append(sample)
        while len(self.transitions) > self.capacity:
            del self.transitions[0]

class PrioritizedReplayBuffer(ReplayBuffer):
    """
    A prioritized replay buffer with loss-proportional
    sampling.

    Weights passed to add_sample() and update_weights()
    are assumed to be error terms (e.g. the absolute TD
    error).
    """
    # pylint: disable=R0913
    def __init__(self, capacity, alpha, beta, default_init_weight=1e5, epsilon=0):
        """
        Create a prioritized replay buffer.

        Args:
          capacity: the maximum number of transitions to
            store in the buffer.
          alpha: an exponent controlling the temperature.
            Higher values result in more prioritization.
            A value of 0 yields uniform prioritization.
          beta: an exponent controlling the amount of
            importance sampling. A value of 1 yields
            unbiased sampling. A value of 0 yields no
            importance sampling.
          default_init_weight: the initial weight for new
            samples when add_sample() is called without an
            init_weight argument.
          epsilon: a value which is added to every error
            term before the error term is used.
        """
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.default_init_weight = default_init_weight
        self.epsilon = epsilon
        self.transitions = []
        self.errors = []

    @property
    def size(self):
        return len(self.transitions)

    def sample(self, num_samples):
        probs = np.power(np.array(self.errors), self.alpha).astype('float64')
        probs /= np.sum(probs)
        sampled_indices = np.random.choice(len(probs), size=num_samples, replace=False, p=probs)
        importance_weights = np.power(probs[sampled_indices] * self.size, -self.beta)
        importance_weights /= np.amax(importance_weights)
        samples = []
        for i, weight in zip(sampled_indices, importance_weights):
            sample = self.transitions[i].copy()
            sample['weight'] = weight
            sample['id'] = i
            samples.append(sample)
        return samples

    def add_sample(self, sample, init_weight=None):
        self.transitions.append(sample)
        if init_weight is None:
            self.errors.append(self.default_init_weight)
        else:
            self.errors.append(init_weight + self.epsilon)
        while self.size > self.capacity:
            del self.transitions[0]
            del self.errors[0]

    def update_weights(self, samples, new_weights):
        for sample, weight in zip(samples, new_weights):
            self.errors[sample['id']] = weight + self.epsilon
