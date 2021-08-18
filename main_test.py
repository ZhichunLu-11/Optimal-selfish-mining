import datetime

import mdptoolbox
import numpy as np
import pandas as pd
from numpy.core.fromnumeric import size
from numpy.core.numeric import Inf
from numpy.lib.index_tricks import IndexExpression
from scipy.sparse import csr_matrix as sparse

IRRELEVANT, RELEVANT, ACTIVE = 0, 1, 2

ADOPT, OVERRIDE, WAIT, MATCH = 0, 1, 2, 3

UNDERPAYING = 0
OVERPAYING = 1

states = dict()
states[0] = "IRRELEVANT"
states[1] = "RELEVANT"
states[2] = "ACTIVE"


actions = dict()
actions[0] = "ADOPT"
actions[1] = "OVERRIDE"
actions[2] = "WAIT"
actions[3] = "MATCH"


def overpaying_reward_agh(rho, alpha, a, h):
    return (1-rho)*(alpha*(1-alpha)/pow(1-2*alpha, 2))+1/2*((a-h)/(1-2*alpha)+a+h)


def overpaying_reward_hga(rho, alpha, a, h):
    return (1-pow(alpha/(1-alpha), h-a))*(-rho*h)+pow(alpha/(1-alpha), h-a)*(1-rho)*(alpha*(1-alpha)/pow(1-2*alpha, 2)+(h-a)/(1-2*alpha))


def get_index(a, h, f, rounds, fork_states_num):
    return a * rounds * fork_states_num + h * fork_states_num + f


def get_state(index, rounds, fork_states_num):
    a, remainder = divmod(index, rounds*fork_states_num)
    h, f = divmod(remainder, fork_states_num)
    return "({}, {}, {})".format(a, h, states[f])


def clear_value_in_diagonal(matrix, indexs):
    for index in indexs:
        matrix[index][index] = 0


def monitor_value(matrix, a, h, f, rounds, fork_states_num):
    index = get_index(a, h, f, rounds, fork_states_num)
    return matrix[index][index]


def generate_probability_matrix(states_num, action_num, rounds, fork_states_num, alpha, gamma):

    P = np.zeros([action_num, states_num, states_num])

    for action in [OVERRIDE, WAIT, MATCH]:
        np.fill_diagonal(P[action], 1)
    # the structure of probability is (A, H, F)
    # irrelevant = 0, relevant =1, active = 2
    # (0, 0, irrelevant)
    # (0, 0, relevant)
    # (0, 0, active)
    # (0, 1, irrelevant)
    # (0, 1, relevant)
    # (0, 1, active)
    # ...
    # (0, 75, active)
    # (1, 0, irrelevant)

    # probability under action adopt.
    # with probablity alpha to (1, 0, IRRELEVANT) position
    adversary_height, honest_height = 1, 0
    index_column_current = get_index(adversary_height, honest_height,
                                     IRRELEVANT, rounds, fork_states_num)
    P[ADOPT, :, index_column_current] += alpha

    # with probablity 1 - alpha to (0, 1, IRRELEVANT) I am not sure if it should be (0, 1, RELEVANT)
    # 可能是错的。
    adversary_height, honest_height = 0, 1
    index_column_current = get_index(adversary_height, honest_height,
                                     IRRELEVANT, rounds, fork_states_num)
    P[ADOPT, :, index_column_current] += 1-alpha

    # probability under action override.
    # only works for a > h.
    # I am wrong at the first attempt. PLZ remember it !!!
    for a in range(0, rounds-1):
        for h in range(0, rounds-1):
            if a > h:
                index_row_begin = get_index(
                    a, h, IRRELEVANT, rounds, fork_states_num)
                index_row_end = get_index(
                    a, h, ACTIVE, rounds, fork_states_num)

                clear_value_in_diagonal(
                    P[OVERRIDE], range(index_row_begin, index_row_end+1))

                # with probablity alpha to ((a - h), 0, 0).
                index_column_current = get_index(
                    (a-h), 0, IRRELEVANT, rounds, fork_states_num)
                P[OVERRIDE, index_row_begin:index_row_end+1,
                    index_column_current] += alpha

                # with probablity alpha to ((a - h - 1), 1, 1).
                index_column_current = get_index(
                    (a-h-1), 1, RELEVANT, rounds, fork_states_num)
                P[OVERRIDE, index_row_begin:index_row_end+1,
                    index_column_current] += 1-alpha

    # probability under action wait.
    for a in range(0, rounds-1):
        for h in range(0, rounds-1):
            # IRRELEVANT
            index_row = get_index(
                a, h, IRRELEVANT, rounds, fork_states_num)
            clear_value_in_diagonal(P[WAIT], [index_row])
            P[WAIT, index_row, get_index(
                a+1, h, IRRELEVANT, rounds, fork_states_num)] += alpha
            P[WAIT, index_row, get_index(
                a, h+1, RELEVANT, rounds, fork_states_num)] += 1-alpha

            # RELEVANT
            index_row += 1
            clear_value_in_diagonal(P[WAIT], [index_row])
            P[WAIT, index_row, get_index(
                a+1, h, IRRELEVANT, rounds, fork_states_num)] += alpha
            P[WAIT, index_row, get_index(
                a, h+1, RELEVANT, rounds, fork_states_num)] += 1-alpha

            # ACTIVE
            index_row += 1
            clear_value_in_diagonal(P[WAIT], [index_row])
            P[WAIT, index_row, get_index(
                a+1, h, ACTIVE, rounds, fork_states_num)] += alpha
            #  这里错了，要注意。
            P[WAIT, index_row, get_index(
                a-h, 1, RELEVANT, rounds, fork_states_num)] += gamma*(1-alpha)
            P[WAIT, index_row, get_index(
                a, h+1, RELEVANT, rounds, fork_states_num)] += (1-gamma)*(1-alpha)

    # probability under action match.
    for a in range(0, rounds-1):
        for h in range(0, rounds-1):
            if a >= h:
                index_row = get_index(
                    a, h, RELEVANT, rounds, fork_states_num)
                clear_value_in_diagonal(P[MATCH], [index_row])
                P[MATCH, index_row, get_index(
                    a+1, h, ACTIVE, rounds, fork_states_num)] += alpha
                P[MATCH, index_row, get_index(
                    a-h, 1, RELEVANT, rounds, fork_states_num)] += gamma*(1-alpha)
                P[MATCH, index_row, get_index(
                    a, h+1, RELEVANT, rounds, fork_states_num)] += (1-gamma)*(1-alpha)

    P = [sparse(P[ADOPT]), sparse(P[OVERRIDE]),
         sparse(P[WAIT]), sparse(P[MATCH])]

    return P


def generate_reward_matrix(states_num, action_num, rounds, fork_states_num, alpha, rho, pay_type):
    R = np.zeros([action_num, states_num, states_num])

    for action in [OVERRIDE, WAIT, MATCH]:
        np.fill_diagonal(R[action], -100000)

    # reward under action adopt.
    for a in range(0, rounds):
        for h in range(0, rounds):
            index_row_begin = get_index(
                a, h, IRRELEVANT, rounds, fork_states_num)
            index_row_end = index_row_begin+2

            adversary_height, honest_height = 1, 0
            index_column_current = get_index(adversary_height, honest_height,
                                             IRRELEVANT, rounds, fork_states_num)
            if pay_type == UNDERPAYING:
                R[ADOPT, index_row_begin:index_row_end +
                    1, index_column_current] += -rho * h
            else:
                if a == rounds-1:
                    R[ADOPT, index_row_begin:index_row_end +
                      1, index_column_current] += (1-rho) * overpaying_reward_agh(rho, alpha, a, h)
                elif h == rounds-1:
                    R[ADOPT, index_row_begin:index_row_end +
                      1, index_column_current] += (1-rho)*overpaying_reward_hga(rho, alpha, a, h)
                else:
                    R[ADOPT, index_row_begin:index_row_end +
                        1, index_column_current] += -rho * h

            adversary_height, honest_height = 0, 1
            index_column_current = get_index(adversary_height, honest_height,
                                             IRRELEVANT, rounds, fork_states_num)
            if pay_type == UNDERPAYING:
                R[ADOPT, index_row_begin:index_row_end +
                    1, index_column_current] += -rho * h
            else:
                if a == rounds-1:
                    R[ADOPT, index_row_begin:index_row_end +
                      1, index_column_current] += (1-rho) * overpaying_reward_agh(rho, alpha, a, h)
                elif h == rounds-1:
                    R[ADOPT, index_row_begin:index_row_end +
                      1, index_column_current] += (1-rho)*overpaying_reward_hga(rho, alpha, a, h)
                else:
                    R[ADOPT, index_row_begin:index_row_end +
                        1, index_column_current] += -rho * h

    # reward under action override.
    for a in range(0, rounds-1):
        for h in range(0, rounds-1):
            if a > h:
                index_row_begin = get_index(
                    a, h, IRRELEVANT, rounds, fork_states_num)
                index_row_end = index_row_begin+2

                clear_value_in_diagonal(
                    R[OVERRIDE], range(index_row_begin, index_row_end+1))

                index_column_current = get_index(
                    (a-h), 0, IRRELEVANT, rounds, fork_states_num)
                R[OVERRIDE, index_row_begin:index_row_end+1,
                    index_column_current] += (1-rho) * (h+1)
                index_column_current = get_index(
                    (a-h-1), 1, RELEVANT, rounds, fork_states_num)
                R[OVERRIDE, index_row_begin:index_row_end+1,
                    index_column_current] += (1-rho) * (h+1)

    # reward under action wait.
    for a in range(0, rounds-1):
        for h in range(0, rounds-1):
            # ACTIVE
            index_row = get_index(
                a, h, ACTIVE, rounds, fork_states_num)
            clear_value_in_diagonal(
                R[WAIT], [index_row])
            R[WAIT, index_row, get_index(
                a-h, 1, RELEVANT, rounds, fork_states_num)] += (1-rho)*h

    # reward under action match.
    for a in range(0, rounds-1):
        for h in range(0, rounds-1):
            if a >= h:
                index_row = get_index(
                    a, h, RELEVANT, rounds, fork_states_num)
                clear_value_in_diagonal(
                    R[MATCH], [index_row])
                R[MATCH, index_row, get_index(
                    a-h, 1, RELEVANT, rounds, fork_states_num)] += (1-rho)*h

    R = [sparse(R[ADOPT]), sparse(R[OVERRIDE]),
         sparse(R[WAIT]), sparse(R[MATCH])]
    return R


if __name__ == "__main__":
    starttime = datetime.datetime.now()
    low, high, epsilon = 0, 1, pow(10, -5)
    rounds = 96

    # There are three different fork for the sanme height combination.
    states_num = rounds*rounds*3
    # four actions: adopt, override, wait, match.
    action_num, fork_states_num = 4, 3
    gamma = 0
    for alpha in [450]:
        alpha /= 1000
        # generate P.
        P = generate_probability_matrix(
            states_num, action_num, rounds, fork_states_num, alpha, gamma)

        # UNDERPAYING
        while high-low > epsilon/8:
            rho = (low+high)/2
            # generate Reward with different rho.
            R = generate_reward_matrix(
                states_num, action_num, rounds, fork_states_num, alpha, rho, UNDERPAYING)

            rvi = mdptoolbox.mdp.RelativeValueIteration(P, R)
            rvi.run()
            if rvi.average_reward > 0:
                low = rho
            else:
                high = rho
        print("low bound: alpha: {}, gamma: {}, rho: {}".format(alpha, gamma, rho))

        # OVERPAYING
        low = rho
        high = min(rho + 0.1, 1)

        while high-low > epsilon/8:
            rho = (low+high)/2

            # generate Reward with different rho.
            R = generate_reward_matrix(
                states_num, action_num, rounds, fork_states_num, alpha, rho, OVERPAYING)
            # for action in [OVERPAYING, WAIT, MATCH]:
            rvi = mdptoolbox.mdp.RelativeValueIteration(P, R)
            rvi.run()
            if rvi.average_reward > 0:
                low = rho
            else:
                high = rho
        print("high bound: alpha: {}, gamma: {}, rho: {}".format(alpha, gamma, rho))
