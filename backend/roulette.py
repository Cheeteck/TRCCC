import random

roulette_numbers = [
    {'num': 0, 'color': 'green'}, {'num': 32, 'color': 'red'}, {'num': 15, 'color': 'black'},
    {'num': 19, 'color': 'red'}, {'num': 4, 'color': 'black'}, {'num': 21, 'color': 'red'},
    {'num': 2, 'color': 'black'}, {'num': 25, 'color': 'red'}, {'num': 17, 'color': 'black'},
    {'num': 34, 'color': 'red'}, {'num': 6, 'color': 'black'}, {'num': 27, 'color': 'red'},
    {'num': 13, 'color': 'black'}, {'num': 36, 'color': 'red'}, {'num': 11, 'color': 'black'},
    {'num': 30, 'color': 'red'}, {'num': 8, 'color': 'black'}, {'num': 23, 'color': 'red'},
    {'num': 10, 'color': 'black'}, {'num': 5, 'color': 'red'}, {'num': 24, 'color': 'black'},
    {'num': 16, 'color': 'red'}, {'num': 33, 'color': 'black'}, {'num': 1, 'color': 'red'},
    {'num': 20, 'color': 'black'}, {'num': 14, 'color': 'red'}, {'num': 31, 'color': 'black'},
    {'num': 9, 'color': 'red'}, {'num': 22, 'color': 'black'}, {'num': 18, 'color': 'red'},
    {'num': 29, 'color': 'black'}, {'num': 7, 'color': 'red'}, {'num': 28, 'color': 'black'},
    {'num': 12, 'color': 'red'}, {'num': 35, 'color': 'black'}, {'num': 3, 'color': 'red'},
    {'num': 26, 'color': 'black'}
]

payouts = {
    'number': 35,
    'color': 1,
    'evenodd': 1,
    'dozen': 2,
    'column': 2,
}

def spin_wheel():
    return random.choice(roulette_numbers)

def calculate_payout(bets, spin_result):
    n = spin_result['num']
    c = spin_result['color']
    total_bet = 0
    payout = 0

    if 'number' in bets:
        for chosen_num, amount in bets['number']:
            total_bet += amount
            if chosen_num == n:
                payout += amount * payouts['number']

    if 'color' in bets and c != 'green':
        for color_choice, amount in bets['color']:
            total_bet += amount
            if c == color_choice:
                payout += amount * payouts['color']

    if 'evenodd' in bets and n != 0:
        for eo_choice, amount in bets['evenodd']:
            total_bet += amount
            if (eo_choice == 'even' and n % 2 == 0) or (eo_choice == 'odd' and n % 2 == 1):
                payout += amount * payouts['evenodd']

    if 'dozen' in bets and n != 0:
        for dozen_choice, amount in bets['dozen']:
            total_bet += amount
            if in_dozen(n, dozen_choice):
                payout += amount * payouts['dozen']

    if 'column' in bets and n != 0:
        for column_choice, amount in bets['column']:
            total_bet += amount
            if in_column(n, column_choice):
                payout += amount * payouts['column']

    net_profit = payout - total_bet
    return payout, total_bet, net_profit

