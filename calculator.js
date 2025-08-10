const express = require('express');
const winston = require('winston');
const { MongoClient, ObjectId } = require('mongodb');

const app = express();
const port = 3000;

// Declaring mongo url and db variable

const mongoUri = process.env.MONGO_URI;
let db;

app.use(express.json());

// Winston logger config

const logger = winston.createLogger({
    level: 'info',
    format: winston.format.json(),
    defaultMeta: { service: 'calculator-microservice' },
    transports: [
        new winston.transports.Console({ format: winston.format.simple() }),
        new winston.transports.File({ filename: 'logs/error.log', level: 'error' }),
        new winston.transports.File({ filename: 'logs/combined.log' })
    ]
});

// Connect to MongoDB
MongoClient.connect(mongoUri)
    .then(client => {
        db = client.db('CalculatorMicroservice');
        logger.info('Connected to MongoDB');
    })
    .catch(err => {
        logger.error('Failed to connect to MongoDB', err);
    });

// Request logging middleware
app.use((req, res, next) => {
    logger.info(`Request: ${req.method} ${req.url}`);
    next();
});

// Middleware to validate and parse input

function validateInput(req, res, next) {
    const { num1, num2 } = req.query;
    req.num1 = parseFloat(num1);
    req.num2 = parseFloat(num2);
    if (isNaN(req.num1) || isNaN(req.num2)) {
        return res.status(400).json({ error: 'num1 and num2 must be valid numbers' });
    }
    next();
}

// Save operation to DB
async function logToDB(operation, result, req) {
    if (!db) return;
    const doc = {
        operation,
        num1: req.num1,
        num2: req.num2,
        result
    };
    await db.collection('operations').insertOne(doc);
    logger.info(`Inserted to DB: ${JSON.stringify(doc)}`);
}

// Additiom

app.get('/add', validateInput, async (req, res) => {
    const result = req.num1 + req.num2;
    await logToDB('add', result, req);
    res.json({ result });
});

// Subtraction

app.get('/subtract', validateInput, async (req, res) => {
    const result = req.num1 - req.num2;
    await logToDB('subtract', result, req);
    res.json({ result });
});

//Multiplication

app.get('/multiply', validateInput, async (req, res) => {
    const result = req.num1 * req.num2;
    await logToDB('multiply', result, req);
    res.json({ result });
});

//Division

app.get('/divide', validateInput, async (req, res) => {
    if (req.num2 === 0) return res.status(400).json({ error: 'Division by zero' });
    const result = req.num1 / req.num2;
    await logToDB('divide', result, req);
    res.json({ result });
});

// CRUD Endpoints for /operations

// CREATE

app.post('/operations', async (req, res) => {
    try {
        const doc = req.body;
        const result = await db.collection('operations').insertOne(doc);
        res.status(201).json({ _id: result.insertedId });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// READ

app.get('/operations', async (req, res) => {
    try {
        const ops = await db.collection('operations').find().toArray();
        res.json(ops);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

//UPDATE

app.put('/operations/:id', async (req, res) => {
    try {
        const result = await db.collection('operations').updateOne(
            { _id: new ObjectId(req.params.id) },
            { $set: req.body }
        );
        if (result.matchedCount === 0) return res.status(404).json({ error: 'Not found' });
        res.json({ updated: result.modifiedCount });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// DELETE

app.delete('/operations/:id', async (req, res) => {
    try {
        const result = await db.collection('operations').deleteOne({ _id: new ObjectId(req.params.id) });
        if (result.deletedCount === 0) return res.status(404).json({ error: 'Not found' });
        res.json({ deleted: result.deletedCount });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});
// 404 error handler
app.use((req, res) => {
    logger.warn(`Invalid endpoint accessed: ${req.method} ${req.originalUrl}`);
    res.status(404).json({ error: 'Invalid endpoint. Use /add, /subtract, /multiply, /divide, /power, /modulo, /sqrt or /percentage with num1 and num2 query parameters. or /operations to view all data from Database' });
});

// Start server
app.listen(port, () => {
    logger.info(`Calculator running at http://localhost:${port}`);
});
