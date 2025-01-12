from keras.layers import (Dense, Dropout, Embedding, Conv1D, PReLU,
                          SpatialDropout1D, concatenate, Flatten, MaxPooling1D,
                          BatchNormalization)
from keras.models import Model, Input


from src.models.nn.model import GeneralLSTM
from src.models.nn.janet import JANET


class bigLSTM(GeneralLSTM):
    def __init__(self,
                 data,
                 eqt_embeddings_size=80,
                 lstm_out_dim=64,
                 use_lstm=True,
                 dropout_rate=0.8,
                 dropout_spatial_rate=0.5,
                 dropout_lstm=0.3,
                 dropout_lstm_rec=0.3,
                 kernel_size=3,
                 loss='binary_crossentropy',
                 optimizer=None):

        super(bigLSTM, self).__init__(
            data,
            eqt_embeddings_size=eqt_embeddings_size,
            lstm_out_dim=lstm_out_dim,
            use_lstm=use_lstm,
            dropout_rate=dropout_rate,
            dropout_spatial_rate=dropout_spatial_rate,
            dropout_lstm=dropout_lstm,
            dropout_lstm_rec=dropout_lstm_rec,
            kernel_size=kernel_size,
            loss=loss,
            optimizer=optimizer)

        self.model, self.inputnames = self.create_model()
                
    def create_model(self):
        # First create the eqt embeddings
        eqt_code_input = Input(shape=[1], name='eqt_code_input')
        eqt_emb = Embedding(
            output_dim=self.eqt_embeddings_size,
            input_dim=self.n_eqt + 1,
            input_length=1,
            name='eqt_embeddings')(eqt_code_input)
        eqt_emb = SpatialDropout1D(self.dropout_spatial_rate)(eqt_emb)
        eqt_emb = Flatten()(eqt_emb)

        # Then the LSTM/CNN1D for the returns time series
        returns_input = Input(
            shape=(self.returns_length, 1), name='returns_input')

        if self.use_lstm:
            returns_lstm = JANET(
                self.lstm_out_dim,
                return_sequences=False,
                dropout=0.3,
                recurrent_dropout=0.3)(returns_input)
        else:
            returns_lstm = Conv1D(
                filters=self.lstm_out_dim,
                kernel_size=self.kernel_size,
                activation='linear',
                name='returns_conv')(returns_input)
            returns_lstm = Dropout(self.dropout_rate)(returns_lstm)
            returns_lstm = MaxPooling1D()(returns_lstm)
            returns_lstm = Flatten()(returns_lstm)
        returns_lstm = Dense(32, activation='linear')(returns_lstm)
        returns_lstm = Dropout(self.dropout_rate)(returns_lstm)
        returns_lstm = PReLU()(returns_lstm)

        # and the the LSTM/CNN part for the volatility time series
        vol_input = Input(shape=(self.returns_length, 1), name='vol_input')

        if self.use_lstm:
            vol_lstm = JANET(
                self.lstm_out_dim, return_sequences=False)(vol_input)
        else:
            vol_lstm = Conv1D(
                filters=self.lstm_out_dim,
                kernel_size=self.kernel_size,
                activation='linear',
                name='vol_conv')(vol_input)
            vol_lstm = Dropout(self.dropout_rate)(vol_lstm)
            vol_lstm = MaxPooling1D()(vol_lstm)
            vol_lstm = Flatten()(vol_lstm)
        vol_lstm = Dense(32, activation='linear')(vol_lstm)
        vol_lstm = Dropout(self.dropout_rate)(vol_lstm)
        vol_lstm = PReLU()(vol_lstm)

        x = concatenate([eqt_emb, returns_lstm, vol_lstm])
        x = Dense(128, activation='linear')(x)
        x = PReLU()(x)

        # Finally concatenate the handmade features and the one from
        # the embeddings from the lstms/convolutions

        handmade_features_input = Input(
            shape=(len(self.non_return_cols), ),
            name='handmade_features_input')

        x = concatenate([handmade_features_input, x])
        x = Dense(128, activation='linear')(x)
        x = PReLU()(x)
        x = BatchNormalization()(x)
        x = Dropout(self.dropout_rate)(x)
        x = Dense(64, activation='linear')(x)
        x = PReLU()(x)
        x = BatchNormalization()(x)
        x = Dropout(self.dropout_rate)(x)
        output = Dense(2, activation='softmax')(x)

        model = Model(
            inputs=[
                eqt_code_input, returns_input, vol_input,
                handmade_features_input
            ],
            outputs=[output])

        inputs = [
            "eqt_code_input", "returns_input", "vol_input",
            "handmade_features_input"
        ]
        return model, inputs


if __name__ == '__main__':
    from src.tools.experiment import Experiment
    from src.tools.dataloader import Data
    from src.tools.utils import plot_training
    from keras.utils import plot_model
    
    exp = Experiment(modelname="janet_droupout")

    data = Data(small=True, verbose=True)
    exp.addconfig("data", data.config)

    model = bigLSTM(data, use_lstm=True)
    exp.addconfig("model", model.config)

    plot_model(model.model, to_file=exp.pnggraph, show_shapes=True)

    # Fit the model
    history = model.compile_fit(
        checkpointname=exp.modelname,
        epochs=100,
        plateau_patience=10,
        verbose=1)

    exp.addconfig("learning", model.learning_config)
    exp.saveconfig(verbose=True)

    plot_training(
        history, show=False, losspath=exp.pngloss, accpath=exp.pngacc)

    # Predict on the test dataset
    model.predict_test(
        exp.modelname,
        bincsv=exp.allpath("predictions_bin.csv"),
        probacsv=exp.allpath("predictions_proba.csv"))
