#!/usr/bin/env python3
"""
Tests for the Social Tokenized UserIDs (STU) model.
"""

import torch
import torch.nn as nn
import pytest
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from next_target_prediction_stu import NextTargetPredictionSTU, STUBatch


class TestNextTargetPredictionSTU:
    """Test suite for the STU model."""
    
    @pytest.fixture
    def model_params(self):
        """Model parameters for testing."""
        return {
            'num_actions': 5,
            'num_codebooks': 3,  # Explicitly set for testing
            'vocab_size': 10000,
            'embedding_dim': 128,
            'hidden_dim': 256,
            'device': 'cpu'
        }
    
    @pytest.fixture
    def batch_params(self):
        """Batch parameters for testing."""
        return {
            'batch_size': 4,
            'history_length': 3
        }
    
    @pytest.fixture
    def model(self, model_params):
        """Create a model instance for testing."""
        return NextTargetPredictionSTU(**model_params)
    
    @pytest.fixture
    def sample_batch(self, model_params, batch_params):
        """Create a sample batch for testing."""
        vocab_size = model_params['vocab_size']
        num_actions = model_params['num_actions']
        num_codebooks = model_params['num_codebooks']
        batch_size = batch_params['batch_size']
        history_length = batch_params['history_length']
        
        history_mask = torch.ones(batch_size, history_length, dtype=torch.float)
        # For robust testing, let's mask the first history item for each example
        if history_length > 0:
            history_mask[:, 0] = 0
        
        return STUBatch(
            actor_stu=torch.randint(0, vocab_size, (batch_size, num_codebooks)),
            actor_history_actions=torch.randint(0, num_actions, (batch_size, history_length)),
            actor_history_targets=torch.randint(0, vocab_size, (batch_size, num_codebooks * history_length)),
            actor_history_mask=history_mask,
            example_action=torch.randint(0, num_actions, (batch_size,)),
            example_target_stu=torch.randint(0, vocab_size, (batch_size, num_codebooks))
        )
    
    def test_model_initialization(self, model_params):
        """Test that the model initializes correctly."""
        model = NextTargetPredictionSTU(**model_params)
        
        # Check that all components are created
        assert hasattr(model, 'action_embedding')
        assert hasattr(model, 'stu_embedding')
        assert hasattr(model, 'user_action_mlp')
        assert hasattr(model, 'tower_layers')
        
        # Check embedding dimensions
        assert model.action_embedding.num_embeddings == model_params['num_actions']
        assert model.action_embedding.embedding_dim == model_params['embedding_dim']
        assert model.stu_embedding.num_embeddings == model_params['vocab_size']
        assert model.stu_embedding.embedding_dim == model_params['embedding_dim']
        
        # Check tower layers
        assert len(model.tower_layers) == model_params['num_codebooks']
        for i, tower in enumerate(model.tower_layers):
            # Check input size: hidden_dim + i * embedding_dim
            expected_input_size = model_params['hidden_dim'] + i * model_params['embedding_dim']
            assert tower[0].in_features == expected_input_size
            assert tower[-1].out_features == model_params['vocab_size']
    
    def test_get_user_action_repr(self, model, sample_batch):
        """Test the user-action representation function."""
        user_action_repr = model.get_user_action_repr(
            sample_batch.actor_stu,
            sample_batch.actor_history_actions,
            sample_batch.actor_history_targets,
            sample_batch.actor_history_mask,
            sample_batch.example_action
        )
        
        # Check output shape
        expected_shape = (sample_batch.actor_stu.shape[0], model.hidden_dim)
        assert user_action_repr.shape == expected_shape
        
        # Check that output is not all zeros
        assert not torch.allclose(user_action_repr, torch.zeros_like(user_action_repr))
    
    def test_predict_token_0(self, model, sample_batch):
        """Test predicting the first token."""
        user_action_repr = model.get_user_action_repr(
            sample_batch.actor_stu,
            sample_batch.actor_history_actions,
            sample_batch.actor_history_targets,
            sample_batch.actor_history_mask,
            sample_batch.example_action
        )
        
        token_0_logits = model.predict_token(user_action_repr, [], 0)
        
        # Check output shape
        expected_shape = (sample_batch.actor_stu.shape[0], model.vocab_size)
        assert token_0_logits.shape == expected_shape
        
        # Check that logits are reasonable (not all the same)
        assert not torch.allclose(token_0_logits, token_0_logits[0].unsqueeze(0).expand_as(token_0_logits))
    
    def test_predict_token_1(self, model, sample_batch):
        """Test predicting the second token."""
        user_action_repr = model.get_user_action_repr(
            sample_batch.actor_stu,
            sample_batch.actor_history_actions,
            sample_batch.actor_history_targets,
            sample_batch.actor_history_mask,
            sample_batch.example_action
        )
        
        token_0 = sample_batch.example_target_stu[:, 0]
        token_1_logits = model.predict_token(user_action_repr, [token_0], 1)
        
        # Check output shape
        expected_shape = (sample_batch.actor_stu.shape[0], model.vocab_size)
        assert token_1_logits.shape == expected_shape
    
    def test_predict_token_2(self, model, sample_batch):
        """Test predicting the third token."""
        user_action_repr = model.get_user_action_repr(
            sample_batch.actor_stu,
            sample_batch.actor_history_actions,
            sample_batch.actor_history_targets,
            sample_batch.actor_history_mask,
            sample_batch.example_action
        )
        
        token_0 = sample_batch.example_target_stu[:, 0]
        token_1 = sample_batch.example_target_stu[:, 1]
        token_2_logits = model.predict_token(user_action_repr, [token_0, token_1], 2)
        
        # Check output shape
        expected_shape = (sample_batch.actor_stu.shape[0], model.vocab_size)
        assert token_2_logits.shape == expected_shape
    
    def test_train_forward_with_target(self, model, sample_batch):
        """Test the complete training forward pass."""
        results = model.train_forward_with_target(sample_batch)
        
        # Check that all expected keys are present
        expected_keys = ['loss', 'loss_0', 'loss_1', 'loss_2', 
                        'accuracy_0', 'accuracy_1', 'accuracy_2', 'overall_accuracy']
        for key in expected_keys:
            assert key in results
        
        # Check that losses are scalars and positive
        assert results['loss'].dim() == 0  # scalar
        assert results['loss'].item() > 0
        assert results['loss_0'].item() > 0
        assert results['loss_1'].item() > 0
        assert results['loss_2'].item() > 0
        
        # Check that accuracies are between 0 and 1
        assert 0 <= results['accuracy_0'].item() <= 1
        assert 0 <= results['accuracy_1'].item() <= 1
        assert 0 <= results['accuracy_2'].item() <= 1
        assert 0 <= results['overall_accuracy'].item() <= 1
        
        # Check that total loss is sum of individual losses
        expected_total = results['loss_0'] + results['loss_1'] + results['loss_2']
        assert torch.allclose(results['loss'], expected_total, atol=1e-6)
    
    def test_empty_history(self, model, model_params, batch_params):
        """Test behavior with empty history."""
        vocab_size = model_params['vocab_size']
        num_actions = model_params['num_actions']
        num_codebooks = model_params['num_codebooks']
        batch_size = batch_params['batch_size']
        
        # Create batch with empty history
        empty_batch = STUBatch(
            actor_stu=torch.randint(0, vocab_size, (batch_size, num_codebooks)),
            actor_history_actions=torch.empty(batch_size, 0, dtype=torch.long),
            actor_history_targets=torch.empty(batch_size, 0, dtype=torch.long),
            actor_history_mask=torch.empty(batch_size, 0, dtype=torch.float),
            example_action=torch.randint(0, num_actions, (batch_size,)),
            example_target_stu=torch.randint(0, vocab_size, (batch_size, num_codebooks))
        )
        
        # Should not raise an error
        results = model.train_forward_with_target(empty_batch)
        assert 'loss' in results
        assert results['loss'].item() > 0
    
    def test_different_batch_sizes(self, model_params):
        """Test that the model works with different batch sizes."""
        model = NextTargetPredictionSTU(**model_params)
        
        for batch_size in [1, 2, 8]:
            vocab_size = model_params['vocab_size']
            num_actions = model_params['num_actions']
            
            batch = STUBatch(
                actor_stu=torch.randint(0, vocab_size, (batch_size, 3)),
                actor_history_actions=torch.randint(0, num_actions, (batch_size, 3)),
                actor_history_targets=torch.randint(0, vocab_size, (batch_size, 9)),
                actor_history_mask=torch.ones(batch_size, 3, dtype=torch.float),
                example_action=torch.randint(0, num_actions, (batch_size,)),
                example_target_stu=torch.randint(0, vocab_size, (batch_size, 3))
            )
            
            results = model.train_forward_with_target(batch)
            assert results['loss'].shape == torch.Size([])  # scalar
            assert results['loss'].item() > 0
    
    def test_device_consistency(self, model_params):
        """Test that the model works on different devices."""
        if torch.cuda.is_available():
            device = 'cuda'
        elif torch.backends.mps.is_available():
            device = 'mps'
        else:
            device = 'cpu'
        
        model_params['device'] = device
        model = NextTargetPredictionSTU(**model_params)
        
        vocab_size = model_params['vocab_size']
        num_actions = model_params['num_actions']
        
        batch = STUBatch(
            actor_stu=torch.randint(0, vocab_size, (4, 3), device=device),
            actor_history_actions=torch.randint(0, num_actions, (4, 3), device=device),
            actor_history_targets=torch.randint(0, vocab_size, (4, 9), device=device),
            actor_history_mask=torch.ones(4, 3, dtype=torch.float, device=device),
            example_action=torch.randint(0, num_actions, (4,), device=device),
            example_target_stu=torch.randint(0, vocab_size, (4, 3), device=device)
        )
        
        results = model.train_forward_with_target(batch)
        assert results['loss'].device.type == torch.device(device).type


if __name__ == "__main__":
    # Run basic test without pytest
    print("Running basic STU model test...")
    
    # Create model and batch
    model = NextTargetPredictionSTU(
        num_actions=5,
        vocab_size=10000,
        embedding_dim=128,
        hidden_dim=256,
        device="cpu"
    )
    
    batch = STUBatch(
        actor_stu=torch.randint(0, 10000, (4, 3)),
        actor_history_actions=torch.randint(0, 5, (4, 3)),
        actor_history_targets=torch.randint(0, 10000, (4, 9)),
        actor_history_mask=torch.ones(4, 3, dtype=torch.float),
        example_action=torch.randint(0, 5, (4,)),
        example_target_stu=torch.randint(0, 10000, (4, 3))
    )
    
    # Test forward pass
    results = model.train_forward_with_target(batch)
    
    print(f"✅ Test passed!")
    print(f"Loss: {results['loss'].item():.4f}")
    print(f"Overall accuracy: {results['overall_accuracy'].item():.4f}")
    print(f"Individual accuracies: {results['accuracy_0'].item():.4f}, {results['accuracy_1'].item():.4f}, {results['accuracy_2'].item():.4f}") 