
# sweep

if not search_resonance_with_phase():
    reset_range()
    print(f'Resonance not found in S11 phase. Scan again.')
    self.state = StatemachineVna.RESULTS_OUTDATED
    return False


if not search_resonance_with_min_swr():
    print(f'Resonance not found with swr.')
    self.state = StatemachineVna.RESULTS_OUTDATED
    return False

find_sweep_start_stop()



def search_resonance_with_phase():
    ...
    set_f_swr_min_Hz = ...


def search_resonance_with_min_swr():
    ...
    set_f_swr_min_Hz = ...
    f_swr_p2_64_l_Hz = None
    f_swr_p2_64_h_Hz = None

    if f_swr_p2_64_l_Hz and f_swr_p2_64_l_Hz:
        f_swr_p2_64_l_Hz = ...
        f_swr_p2_64_h_Hz = ...
