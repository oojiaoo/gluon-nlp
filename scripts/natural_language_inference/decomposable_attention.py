# pylint: disable=C0103,E1101,R0914
"""
decomposable_attention.py

Part of NLI script of gluon-nlp. Implementation of Decomposable Attentiontion.
Copyright 2018 Mengxiao Lin <linmx0130@gmail.com>.
"""

import mxnet as mx
from mxnet import gluon
from mxnet.gluon import nn


class NLIModel(gluon.HybridBlock):
    """
    A Decomposable Attention Model for Natural Language Inference
    using intra-sentence attention.
    Arxiv paper: https://arxiv.org/pdf/1606.01933.pdf
    """
    def __init__(self, vocab_size, word_embed_size, hidden_size, dropout=0., **kwargs):
        super(NLIModel, self).__init__(**kwargs)
        self.word_embed_size = word_embed_size
        self.hidden_size = hidden_size
        with self.name_scope():
            self.dropout_layer = nn.Dropout(dropout)
            self.word_emb = nn.Embedding(vocab_size, word_embed_size)
            self.lin_proj = nn.Dense(hidden_size, in_units=word_embed_size, activation='relu', flatten=False)
            self.intra_attention = IntraSentenceAttention(hidden_size, hidden_size, dropout)
            self.model = DecomposableAttention(hidden_size*2, hidden_size, 3, dropout)

    def hybrid_forward(self, F, sentence1, sentence2):
        """
        Model forward definition
        """
        feature1 = self.lin_proj(self.dropout_layer(self.word_emb(sentence1)))
        feature1 = F.concat(feature1, self.intra_attention(feature1), dim=-1)
        feature2 = self.lin_proj(self.dropout_layer(self.word_emb(sentence2)))
        feature2 = F.concat(feature2, self.intra_attention(feature2), dim=-1)
        pred = self.model(feature1, feature2)
        return pred

class IntraSentenceAttention(gluon.HybridBlock):
    """
    Intra Sentence Attentiontion block.
    """
    def __init__(self, inp_size: int, hidden_size: int, dropout=0., **kwargs):
        super(IntraSentenceAttention, self).__init__(**kwargs)
        self.hidden_size = hidden_size
        with self.name_scope():
            self.dropout_layer = nn.Dropout(dropout)
            # F_intra in the paper
            self.intra_attn_emb = nn.HybridSequential()
            self.intra_attn_emb.add(self.dropout_layer)
            self.intra_attn_emb.add(nn.Dense(hidden_size, in_units=inp_size, activation='relu', flatten=False))
            self.intra_attn_emb.add(self.dropout_layer)
            self.intra_attn_emb.add(nn.Dense(hidden_size, in_units=hidden_size, activation='relu', flatten=False))
            self.intra_attn_emb.add(nn.Dense(hidden_size, in_units=hidden_size, flatten=False))

    def hybrid_forward(self, F, feature_a):
        # batch_size, length, inp_size = feature_a.shape
        tilde_a = self.intra_attn_emb(feature_a)
        e_matrix = F.batch_dot(tilde_a, tilde_a, transpose_b=True)
        alpha = F.batch_dot(e_matrix.softmax(), tilde_a)
        return alpha

class DecomposableAttention(gluon.HybridBlock):
    """
    Decomposable Attentiontion block.
    """
    def __init__(self, inp_size: int, hidden_size: int, num_class: int, dropout=0., **kwargs):
        super(DecomposableAttention, self).__init__(**kwargs)
        with self.name_scope():
            self.dropout_layer = nn.Dropout(dropout)
            # attention function
            self.f = nn.HybridSequential()
            self.f.add(self.dropout_layer)
            self.f.add(nn.Dense(hidden_size, in_units=inp_size, activation='relu', flatten=False))
            self.f.add(self.dropout_layer)
            self.f.add(nn.Dense(hidden_size, in_units=hidden_size, activation='relu', flatten=False))
            self.f.add(nn.Dense(hidden_size, in_units=hidden_size, flatten=False))
            # compare function
            self.g = nn.HybridSequential()
            self.g.add(self.dropout_layer)
            self.g.add(nn.Dense(hidden_size, in_units=hidden_size * 2, activation='relu', flatten=False))
            self.g.add(self.dropout_layer)
            self.g.add(nn.Dense(hidden_size, in_units=hidden_size, activation='relu', flatten=False))
            self.g.add(nn.Dense(hidden_size, in_units=hidden_size, flatten=False))
            # predictor
            self.h = nn.HybridSequential()
            self.h.add(self.dropout_layer)
            self.h.add(nn.Dense(hidden_size, in_units=hidden_size * 2, activation='relu'))
            self.h.add(self.dropout_layer)
            self.h.add(nn.Dense(hidden_size, in_units=hidden_size, activation='relu'))
            self.h.add(nn.Dense(num_class, in_units=hidden_size))
        # extract features
        self.hidden_size = hidden_size
        self.inp_size = inp_size

    def hybrid_forward(self, F, a, b):
        """
        Forward of Decomposable Attentiontion layer
        """
        # a.shape = [B, L1, H]
        # b.shape = [B, L2, H]
        # extract features
        tilde_a = self.f(a)  # shape = [B, L1, H]
        tilde_b = self.f(b)  # shape = [B, L2, H]
        # attention
        # e.shape = [B, L1, L2]
        e = F.batch_dot(tilde_a, tilde_b, transpose_b=True)
        # beta: b align to a, [B, L1, H]
        beta = F.batch_dot(e.softmax(), tilde_b)
        # alpha: a align to b, [B, L2, H]
        alpha = F.batch_dot(e.transpose([0, 2, 1]).softmax(), tilde_a)
        # compare
        feature1 = self.g(F.concat(tilde_a, beta, dim=2))
        feature2 = self.g(F.concat(tilde_b, alpha, dim=2))
        feature1 = feature1.mean(axis=1)
        feature2 = feature2.mean(axis=1)
        yhat = self.h(F.concat(feature1, feature2, dim=1))
        return yhat
