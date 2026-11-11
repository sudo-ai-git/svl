# svl/rl_compiler.py
# Self-Optimizing Compiler with RL (H49)
# RL agent for guiding compiler optimization passes

from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import random
import math
import json
import hashlib
from collections import defaultdict
from pathlib import Path


class OptimizationPass(Enum):
    """Compiler optimization passes."""
    INLINE = "inline"
    DEAD_CODE_ELIM = "dce"
    CONSTANT_FOLDING = "const_fold"
    LOOP_UNROLL = "loop_unroll"
    LOOP_INVARIANT_CODE_MOTION = "licm"
    COMMON_SUBEXPRESSION_ELIM = "cse"
    STRENGTH_REDUCTION = "strength_red"
    TAIL_CALL_OPT = "tco"
    ESCAPE_ANALYSIS = "escape"
    VECTORIZATION = "vectorize"
    REGISTER_ALLOCATION = "regalloc"
    INSTRUCTION_SCHEDULING = "sched"
    PEEPHOLE = "peephole"
    FUNCTION_SPECIALIZATION = "specialize"


@dataclass
class PassConfig:
    """Configuration for an optimization pass."""
    pass_type: OptimizationPass
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher runs first
    
    def get_param(self, key: str, default: Any = None) -> Any:
        return self.parameters.get(key, default)


@dataclass
class CompilationContext:
    """Context for compilation with RL state."""
    module_name: str
    source_hash: str
    ast_size: int
    function_count: int
    loop_count: int
    memory_ops: int
    call_graph_depth: int
    previous_passes: List[OptimizationPass] = field(default_factory=list)
    performance_history: List[float] = field(default_factory=list)


@dataclass
class RLState:
    """State representation for RL agent."""
    context: CompilationContext
    pass_sequence: List[OptimizationPass] = field(default_factory=list)
    step: int = 0
    total_reward: float = 0.0
    
    def to_feature_vector(self) -> List[float]:
        """Convert state to feature vector for neural network."""
        ctx = self.context
        return [
            ctx.ast_size / 10000.0,  # Normalized
            ctx.function_count / 100.0,
            ctx.loop_count / 50.0,
            ctx.memory_ops / 1000.0,
            ctx.call_graph_depth / 10.0,
            len(self.pass_sequence) / 20.0,
            self.step / 20.0,
            self.total_reward,
        ]


class ReplayBuffer:
    """Experience replay buffer for RL training."""
    
    def __init__(self, capacity: int = 10000):
        self.capacity = capacity
        self.buffer: List[Tuple[RLState, OptimizationPass, float, RLState, bool]] = []
        self.position = 0
    
    def push(self, state: RLState, action: OptimizationPass, reward: float,
             next_state: RLState, done: bool):
        experience = (state, action, reward, next_state, done)
        if len(self.buffer) < self.capacity:
            self.buffer.append(experience)
        else:
            self.buffer[self.position] = experience
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size: int) -> List[Tuple[RLState, OptimizationPass, float, RLState, bool]]:
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))
    
    def __len__(self) -> int:
        return len(self.buffer)


class QNetwork:
    """Simple Q-network for RL agent (using linear approximation for simplicity)."""
    
    def __init__(self, state_dim: int, action_dim: int, learning_rate: float = 0.001):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.learning_rate = learning_rate
        
        # Simple linear Q-function: Q(s,a) = w_a^T * phi(s)
        # In practice, would use a neural network
        self.weights = [[random.gauss(0, 0.01) for _ in range(state_dim)] 
                       for _ in range(action_dim)]
        self.biases = [0.0 for _ in range(action_dim)]
    
    def predict(self, state: RLState) -> List[float]:
        """Predict Q-values for all actions."""
        features = state.to_feature_vector()
        q_values = []
        for a in range(self.action_dim):
            q = self.biases[a]
            for i, f in enumerate(features):
                q += self.weights[a][i] * f
            q_values.append(q)
        return q_values
    
    def update(self, state: RLState, action: OptimizationPass, target: float):
        """Update weights using TD error."""
        features = state.to_feature_vector()
        action_idx = list(OptimizationPass).index(action)
        
        # Current prediction
        pred = self.biases[action_idx]
        for i, f in enumerate(features):
            pred += self.weights[action_idx][i] * f
        
        # TD error
        error = target - pred
        
        # Gradient update
        self.biases[action_idx] += self.learning_rate * error
        for i, f in enumerate(features):
            self.weights[action_idx][i] += self.learning_rate * error * f


class RLAgent:
    """RL agent for compiler optimization."""
    
    def __init__(self, 
                 epsilon: float = 0.1,
                 gamma: float = 0.99,
                 learning_rate: float = 0.001,
                 buffer_capacity: int = 10000):
        self.epsilon = epsilon  # Exploration rate
        self.gamma = gamma      # Discount factor
        self.action_space = list(OptimizationPass)
        self.action_dim = len(self.action_space)
        
        self.state_dim = 8  # Feature vector size
        self.q_network = QNetwork(self.state_dim, self.action_dim, learning_rate)
        self.target_network = QNetwork(self.state_dim, self.action_dim, learning_rate)
        self.replay_buffer = ReplayBuffer(buffer_capacity)
        
        self.training_steps = 0
        self.target_update_freq = 100
    
    def select_action(self, state: RLState, training: bool = True) -> OptimizationPass:
        """Select action using epsilon-greedy policy."""
        if training and random.random() < self.epsilon:
            return random.choice(self.action_space)
        
        q_values = self.q_network.predict(state)
        best_action_idx = q_values.index(max(q_values))
        return self.action_space[best_action_idx]
    
    def compute_reward(self, context: CompilationContext, 
                      before_metrics: Dict[str, float],
                      after_metrics: Dict[str, float]) -> float:
        """Compute reward based on compilation results."""
        reward = 0.0
        
        # Speedup reward (lower is better for compile time, higher for runtime)
        if 'compile_time' in before_metrics and 'compile_time' in after_metrics:
            speedup = before_metrics['compile_time'] / max(after_metrics['compile_time'], 0.001)
            reward += math.log(speedup) * 10.0
        
        if 'runtime' in before_metrics and 'runtime' in after_metrics:
            speedup = before_metrics['runtime'] / max(after_metrics['runtime'], 0.001)
            reward += math.log(speedup) * 20.0
        
        # Code size reduction
        if 'code_size' in before_metrics and 'code_size' in after_metrics:
            reduction = (before_metrics['code_size'] - after_metrics['code_size']) / max(before_metrics['code_size'], 1)
            reward += reduction * 5.0
        
        # Penalty for failed compilation
        if after_metrics.get('compilation_failed', False):
            reward -= 100.0
        
        # Penalty for excessive optimization time
        if 'opt_time' in after_metrics:
            reward -= after_metrics['opt_time'] * 0.1
        
        return reward
    
    def train_step(self, batch_size: int = 32):
        """Perform one training step."""
        if len(self.replay_buffer) < batch_size:
            return
        
        batch = self.replay_buffer.sample(batch_size)
        
        for state, action, reward, next_state, done in batch:
            action_idx = self.action_space.index(action)
            
            # Current Q-value
            current_q = self.q_network.predict(state)[action_idx]
            
            # Target Q-value
            if done:
                target = reward
            else:
                next_q_values = self.target_network.predict(next_state)
                target = reward + self.gamma * max(next_q_values)
            
            # Update Q-network
            self.q_network.update(state, action, target)
        
        self.training_steps += 1
        
        # Update target network periodically
        if self.training_steps % self.target_update_freq == 0:
            self._update_target_network()
    
    def _update_target_network(self):
        """Copy weights from main to target network."""
        self.target_network.weights = [w[:] for w in self.q_network.weights]
        self.target_network.biases = self.q_network.biases[:]
    
    def save_model(self, path: str):
        """Save model to file."""
        data = {
            'weights': self.q_network.weights,
            'biases': self.q_network.biases,
            'epsilon': self.epsilon,
            'gamma': self.gamma,
            'training_steps': self.training_steps,
        }
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def load_model(self, path: str):
        """Load model from file."""
        with open(path, 'r') as f:
            data = json.load(f)
        self.q_network.weights = data['weights']
        self.q_network.biases = data['biases']
        self.epsilon = data['epsilon']
        self.gamma = data['gamma']
        self.training_steps = data['training_steps']
        self._update_target_network()


class SelfOptimizingCompiler:
    """Compiler that uses RL to select optimization passes."""
    
    def __init__(self, rl_agent: Optional[RLAgent] = None):
        self.rl_agent = rl_agent or RLAgent()
        self.pass_registry: Dict[OptimizationPass, Callable] = {}
        self.compilation_history: List[Dict[str, Any]] = []
        self.best_configs: Dict[str, List[PassConfig]] = {}  # module_hash -> best pass configs
    
    def register_pass(self, pass_type: OptimizationPass, 
                     pass_func: Callable[[Any, PassConfig], Any]):
        """Register an optimization pass implementation."""
        self.pass_registry[pass_type] = pass_func
    
    def compile_with_rl(self, module: Any, context: CompilationContext) -> Tuple[Any, Dict[str, Any]]:
        """Compile module using RL-guided optimization."""
        # Get current state
        state = RLState(context=context)
        
        # Select passes using RL agent
        selected_passes = []
        for _ in range(10):  # Max 10 passes per compilation
            action = self.rl_agent.select_action(state, training=True)
            if action not in selected_passes:
                selected_passes.append(action)
                state.pass_sequence.append(action)
                state.step += 1
            else:
                break  # Avoid duplicate passes
        
        # Create pass configs
        pass_configs = [PassConfig(p) for p in selected_passes]
        
        # Apply passes and measure
        before_metrics = self._measure(module)
        optimized_module = self._apply_passes(module, pass_configs)
        after_metrics = self._measure(optimized_module)
        
        # Compute reward
        reward = self.rl_agent.compute_reward(context, before_metrics, after_metrics)
        
        # Create next state
        next_state = RLState(
            context=context,
            pass_sequence=state.pass_sequence.copy(),
            step=state.step + 1,
            total_reward=state.total_reward + reward
        )
        
        # Store experience
        self.rl_agent.replay_buffer.push(state, selected_passes[-1] if selected_passes else OptimizationPass.INLINE, 
                                        reward, next_state, False)
        
        # Train
        self.rl_agent.train_step()
        
        # Record compilation
        compilation_record = {
            'module_hash': context.source_hash,
            'passes': [p.value for p in selected_passes],
            'before_metrics': before_metrics,
            'after_metrics': after_metrics,
            'reward': reward,
        }
        self.compilation_history.append(compilation_record)
        
        # Update best config if improved
        if context.source_hash not in self.best_configs or \
           reward > self._get_best_reward(context.source_hash):
            self.best_configs[context.source_hash] = pass_configs
        
        return optimized_module, {
            'passes': [p.value for p in selected_passes],
            'metrics': after_metrics,
            'reward': reward,
        }
    
    def _get_best_reward(self, module_hash: str) -> float:
        """Get best reward for module."""
        if module_hash not in self.best_configs:
            return float('-inf')
        # Find in history
        for record in reversed(self.compilation_history):
            if record['module_hash'] == module_hash:
                return record['reward']
        return float('-inf')
    
    def _measure(self, module: Any) -> Dict[str, float]:
        """Measure module metrics (placeholder)."""
        # In real implementation, would measure actual compile time, runtime, code size
        return {
            'compile_time': random.uniform(0.1, 1.0),
            'runtime': random.uniform(0.01, 0.1),
            'code_size': random.randint(1000, 10000),
            'compilation_failed': False,
        }
    
    def _apply_passes(self, module: Any, configs: List[PassConfig]) -> Any:
        """Apply optimization passes to module."""
        result = module
        for config in configs:
            if config.enabled and config.pass_type in self.pass_registry:
                try:
                    result = self.pass_registry[config.pass_type](result, config)
                except Exception as e:
                    # Pass failed, continue with next
                    pass
        return result
    
    def get_best_config(self, module_hash: str) -> Optional[List[PassConfig]]:
        """Get best known configuration for module."""
        return self.best_configs.get(module_hash)
    
    def export_history(self, path: str):
        """Export compilation history."""
        data = {
            'history': self.compilation_history,
            'best_configs': {k: [c.pass_type.value for c in v] 
                           for k, v in self.best_configs.items()},
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)


# Example pass implementations (simplified)
def inline_pass(module: Any, config: PassConfig) -> Any:
    """Function inlining pass."""
    threshold = config.get_param('threshold', 250)
    # In real implementation, would inline small functions
    return module

def dce_pass(module: Any, config: PassConfig) -> Any:
    """Dead code elimination pass."""
    return module

def const_fold_pass(module: Any, config: PassConfig) -> Any:
    """Constant folding pass."""
    return module

def loop_unroll_pass(module: Any, config: PassConfig) -> Any:
    """Loop unrolling pass."""
    factor = config.get_param('factor', 4)
    return module

def licm_pass(module: Any, config: PassConfig) -> Any:
    """Loop invariant code motion pass."""
    return module

def cse_pass(module: Any, config: PassConfig) -> Any:
    """Common subexpression elimination pass."""
    return module


# Register default passes
DEFAULT_PASSES = {
    OptimizationPass.INLINE: inline_pass,
    OptimizationPass.DEAD_CODE_ELIM: dce_pass,
    OptimizationPass.CONSTANT_FOLDING: const_fold_pass,
    OptimizationPass.LOOP_UNROLL: loop_unroll_pass,
    OptimizationPass.LOOP_INVARIANT_CODE_MOTION: licm_pass,
    OptimizationPass.COMMON_SUBEXPRESSION_ELIM: cse_pass,
}


def create_rl_compiler() -> SelfOptimizingCompiler:
    """Create a self-optimizing compiler with default passes."""
    agent = RLAgent()
    compiler = SelfOptimizingCompiler(agent)
    
    for pass_type, pass_func in DEFAULT_PASSES.items():
        compiler.register_pass(pass_type, pass_func)
    
    return compiler


if __name__ == '__main__':
    # Test RL compiler
    print("=== RL Compiler Test ===")
    
    compiler = create_rl_compiler()
    
    # Create test context
    context = CompilationContext(
        module_name="test",
        source_hash="abc123",
        ast_size=1000,
        function_count=10,
        loop_count=5,
        memory_ops=100,
        call_graph_depth=3,
    )
    
    # Dummy module
    class DummyModule:
        pass
    
    module = DummyModule()
    
    # Compile with RL
    print("Compiling with RL-guided optimization...")
    optimized, result = compiler.compile_with_rl(module, context)
    
    print(f"Selected passes: {result['passes']}")
    print(f"Reward: {result['reward']:.4f}")
    print(f"Metrics: {result['metrics']}")
    
    # Test multiple compilations
    print("\nRunning multiple compilations for training...")
    for i in range(5):
        opt, res = compiler.compile_with_rl(module, context)
        print(f"  Iteration {i+1}: reward={res['reward']:.4f}, passes={res['passes']}")
    
    # Test model save/load
    compiler.rl_agent.save_model("rl_compiler_model.json")
    print("\nModel saved.")
    
    # Create new agent and load
    new_agent = RLAgent()
    new_agent.load_model("rl_compiler_model.json")
    print("Model loaded successfully.")
    
    # Export history
    compiler.export_history("compilation_history.json")
    print("History exported.")