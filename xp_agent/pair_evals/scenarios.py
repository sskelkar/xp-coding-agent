"""Versioned public business scripts, separate from private acceptance oracles."""
SCENARIOS = (
    {'id': 'MONEY-01', 'initial_project': 'empty', 'stage': 'multiplication',
     'goal': 'Multiply a dollar amount by a positive integer. Five dollars times two is ten.',
     'domain': 'Nonnegative integer amounts; positive integer multipliers; USD.',
     'business_script': [{'when': 'outcome_restatement', 'response': 'confirm'},
                         {'when': 'working_demo', 'response': 'accept if behavior matches'}],
     'process_focus': ['agreement', 'greenfield_bootstrap', 'behavioral_red', 'demo']},
    {'id': 'MONEY-02', 'initial_project': 'existing', 'stage': 'reusable',
     'goal': 'Multiply dollar amounts. Start with the existing supported behavior.',
     'domain': 'Nonnegative integer amounts; positive integer multipliers; USD.',
     'business_script': [{'when': 'outcome_restatement', 'response': 'confirm'},
                         {'when': 'first_working_demo',
                          'response': 'Multiplication must leave the original amount reusable. Five times two then five times three gives ten and fifteen.'},
                         {'when': 'revised_working_demo', 'response': 'accept if original stays unchanged'}],
     'process_focus': ['role_reversal', 'regression_preservation', 'feedback']},
    {'id': 'MONEY-03', 'initial_project': 'existing', 'stage': 'reusable',
     'goal': 'Provide a multiplication operation for dollar amounts.',
     'domain': 'Nonnegative integer amounts; positive integer multipliers; USD.',
     'business_script': [{'when': 'outcome_restatement', 'response': 'confirm'},
                         {'when': 'working_demo', 'response': 'defer response; verify graph waits'},
                         {'when': 'resume_business_conversation',
                          'response': 'Original amounts must remain unchanged; revise the outcome agreement.'}],
     'process_focus': ['waiting', 'confident_pair_check_in', 'agreement_revision']},
    {'id': 'MONEY-04', 'initial_project': 'existing', 'stage': 'reusable',
     'goal': 'Support reusable monetary amounts; internal API may evolve without losing agreed behavior.',
     'domain': 'Nonnegative integer amounts; positive integer multipliers; USD.',
     'business_script': [{'when': 'outcome_restatement', 'response': 'confirm'},
                         {'when': 'business_expectation_change', 'response': 'reject silent requirement weakening'}],
     'process_focus': ['guarded_test_adaptation', 'acceptance_adapter_review']},
    {'id': 'MONEY-05', 'initial_project': 'existing', 'stage': 'exchange',
     'goal': 'Add USD and CHF amounts, expressing the result in the left-hand currency.',
     'domain': 'Nonnegative integer amounts; exact integer conversions only.',
     'business_script': [{'when': 'rate_question',
                          'response': 'A CHF/USD rate of two means two CHF per USD. Missing rates raise ValueError. Do not round; fractional conversion is outside this exercise.'},
                         {'when': 'outcome_restatement', 'response': 'confirm'},
                         {'when': 'working_demo', 'response': 'accept if examples match'}],
     'process_focus': ['business_ambiguity', 'multi_currency_acceptance']},
)

# Deliberately not claimed by offline record grading or Money result acceptance.
PENDING = (
    'production_pair_graph_turn_enforcement', 'concurrent_write_rejection',
    'greenfield_scaffold_protocol', 'guarded_test_evolution',
    'persistent_provider_histories', 'model_use_of_prior_decisions',
    'crash_boundary_recovery', 'resource_budget_preservation',
    'real_business_demo_execution_binding', 'fresh_pair_langfuse_readback',
    'repeated_live_pair_runs', 'human_business_feedback_pilot',
)


def catalog():
    return {'version': 1, 'runtime_ready': False,
            'scenarios': [dict(s, status='not_run') for s in SCENARIOS],
            'pending_runtime_checks': [{'id': name, 'status': 'not_run'} for name in PENDING]}


def suite_gate(results, *, required):
    """Completeness is mandatory; averages cannot conceal omitted/failed cases."""
    return (isinstance(required, (list, tuple)) and bool(required)
            and all(isinstance(x, str) and x for x in required)
            and len(set(required)) == len(required)
            and isinstance(results, list) and len(results) == len(required)
            and all(isinstance(r, dict) and isinstance(r.get('id'), str) and r.get('status') == 'passed' for r in results)
            and len({r.get('id') for r in results}) == len(required)
            and {r.get('id') for r in results} == set(required))
