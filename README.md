>[!IMPORTANT]
> This is a fork of [poke-env](https://github.com/hsahovic/poke-env) that installs with [`metamon`](https://github.com/UT-Austin-RPL/metamon). It attempts to extend the lifespan of poke-env as it was during Metamon's development: 
> 1. Maintains the original gymnasium interface that existed until v0.8.3. `OpenAIGymEnv` (+ ability to swap in custom Players). Rewards functions that take `last_battle` and `current_battle` as input (+ a speed boost). Removes "observation" system that slows fps and is already handled by Metamon.
> 2. Preserves minor early-generation battle details as they were when Metamon's original models were trained.     
> 3. Tries to bring key fixes/improvements since v0.8.3 that are unrelated to gymnasium.
>
> Please see the main repo [here](https://github.com/hsahovic/poke-env) for any other use case.  I only plan to update this to fix breaking changes to the Showdown sim/request message API. Any improvements to early-generation state tracking/sim protocol are now done in metamon.


## Citing `poke-env`

```bibtex
@misc{poke_env,
    author       = {Haris Sahovic},
    title        = {Poke-env: pokemon AI in python},
    url          = {https://github.com/hsahovic/poke-env}
}
```
